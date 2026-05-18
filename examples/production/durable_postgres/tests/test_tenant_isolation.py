"""Multi-tenant isolation tests (Tier 2.1a / D-TENANT-1..10).

Two test bands:
  - Mocked: charset validation, ContextVar plumbing, fallback semantics,
    operator script tenant-flag enforcement. Run on every CI (~ms).
  - needs_postgres: RLS policy enforcement, SET LOCAL connection-recycling
    regression (advisor BLOCKING #1, 2026-05-18). Only run when POSTGRES_DSN
    is set; CI matrix gates these with the same `needs_postgres` mark as
    test_scheduler_hot_path.py.

What the Postgres tests prove:
  1. RLS WITH CHECK rejects cross-tenant INSERT (tenant A's GUC, tenant B row).
  2. SELECT is RLS-unscoped (scheduler poll sees all tenants).
  3. **Pool recycling regression**: a second connection checkout does NOT
     inherit the previous tenant's `app.tenant_id` GUC when the first call
     used `SET LOCAL` inside a transaction. This is the specific bug class
     the advisor flagged — `SET` without LOCAL would leak; the test catches it.
  4. RLS UPDATE policy rejects mid-flight tenant_id migration.
"""
from __future__ import annotations

import pytest

from adv_multi_agent.core.durable.checkpoint import Checkpoint
from examples.production.durable_postgres.store import (
    MissingTenantContext,
    RESERVED_DEFAULT_TENANT,
    _CURRENT_TENANT,
    _resolve_tenant_id,
    _TENANT_ID_RE,
    reset_tenant_context,
    tenant_context,
)

from .conftest import needs_postgres


# ----------------------------------------------------------------------
# D-TENANT-1: charset validation
# ----------------------------------------------------------------------

def test_tenant_id_charset_accepts_valid():
    for valid in ("tenant-a", "TENANT_A", "_default", "_legacy",
                  "abc123", "a", "_", "a-b-c-1-2-3"):
        assert _TENANT_ID_RE.fullmatch(valid), f"should accept {valid!r}"


def test_tenant_id_charset_rejects_invalid():
    for invalid in ("", "-leading-dash", "has space", "has.dot",
                    "has/slash", "has\\back", "a" * 65,  # too long
                    "unicode-é", "tenant;DROP", "'tenant'"):
        assert not _TENANT_ID_RE.fullmatch(invalid), f"should reject {invalid!r}"


# ----------------------------------------------------------------------
# D-TENANT-5: _resolve_tenant_id two-channel resolution
# ----------------------------------------------------------------------

def test_resolve_explicit_kwarg_wins():
    token = tenant_context("tenant-a")
    try:
        # Even with ContextVar set, explicit kwarg takes precedence.
        assert _resolve_tenant_id("tenant-b") == "tenant-b"
    finally:
        reset_tenant_context(token)


def test_resolve_falls_back_to_contextvar():
    token = tenant_context("tenant-c")
    try:
        assert _resolve_tenant_id(None) == "tenant-c"
    finally:
        reset_tenant_context(token)


def test_resolve_falls_back_to_default_with_warning(recwarn, monkeypatch):
    """D-TENANT-2: no kwarg + no ContextVar → _default + DeprecationWarning."""
    monkeypatch.delenv("DURABLE_REQUIRE_EXPLICIT_TENANT", raising=False)
    # Make sure ContextVar is unset
    token = _CURRENT_TENANT.set(None)
    try:
        result = _resolve_tenant_id(None)
        assert result == RESERVED_DEFAULT_TENANT
        # DeprecationWarning emitted
        assert any(
            issubclass(w.category, DeprecationWarning) and "_default" in str(w.message)
            for w in recwarn
        )
    finally:
        _CURRENT_TENANT.reset(token)


def test_resolve_fails_closed_when_env_var_set(monkeypatch):
    """D-TENANT-2: DURABLE_REQUIRE_EXPLICIT_TENANT=1 → MissingTenantContext."""
    monkeypatch.setenv("DURABLE_REQUIRE_EXPLICIT_TENANT", "1")
    token = _CURRENT_TENANT.set(None)
    try:
        with pytest.raises(MissingTenantContext):
            _resolve_tenant_id(None)
    finally:
        _CURRENT_TENANT.reset(token)


def test_resolve_rejects_invalid_kwarg():
    with pytest.raises(ValueError, match="invalid tenant_id"):
        _resolve_tenant_id("has space")


def test_tenant_context_rejects_invalid():
    with pytest.raises(ValueError, match="invalid tenant_id"):
        tenant_context("has;DROP")


@pytest.mark.asyncio
async def test_tenant_context_per_task_isolation():
    """ContextVar is per-asyncio-task; tasks don't see each other's tenant."""
    import asyncio

    results: dict[str, str] = {}

    async def inner(tenant_id: str) -> None:
        token = tenant_context(tenant_id)
        try:
            # Yield to give the other task a chance to set its own ContextVar.
            await asyncio.sleep(0.001)
            results[tenant_id] = _resolve_tenant_id(None)
        finally:
            reset_tenant_context(token)

    await asyncio.gather(inner("tenant-a"), inner("tenant-b"))
    assert results == {"tenant-a": "tenant-a", "tenant-b": "tenant-b"}


# ----------------------------------------------------------------------
# D-TENANT-10: operator script tenant-flag enforcement
# ----------------------------------------------------------------------

def test_list_quarantined_rejects_missing_tenant_flag():
    """list_quarantined.py --tenant is required (argparse fails-fast)."""
    import subprocess
    import sys

    # Invoke the script with no --tenant; argparse should exit 2.
    result = subprocess.run(
        [sys.executable, "-m",
         "examples.production.durable_postgres.scripts.list_quarantined"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "tenant" in (result.stderr + result.stdout).lower()


def test_requeue_rejects_missing_tenant_flag():
    """requeue.py --tenant is required (argparse fails-fast)."""
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, "-m",
         "examples.production.durable_postgres.scripts.requeue",
         "run-abc"],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "tenant" in (result.stderr + result.stdout).lower()


# ----------------------------------------------------------------------
# D-TENANT-3: Postgres RLS enforcement (live DB required)
# ----------------------------------------------------------------------

def _make_checkpoint(run_id: str) -> Checkpoint:
    """Minimal valid Checkpoint for store.write tests."""
    return Checkpoint(
        run_id=run_id,
        schema_version=1,
        status="paused",
        round=0,
        rounds_history=[],
        last_request_json="{}",
        pause_reason="test",
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-18T00:00:00+00:00",
        updated_at="2026-05-18T00:00:00+00:00",
    )


@needs_postgres
async def test_rls_insert_requires_matching_guc(pg_pool, fresh_checkpoints_table):
    """RLS INSERT policy rejects rows whose tenant_id != current_setting GUC."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool, default_workflow_class="W")
    cp = _make_checkpoint("rls-a")

    # Explicit tenant=A; INSERT should succeed.
    await store.write(cp, tenant_id="tenant-a")

    # Now try to INSERT with tenant=B kwarg but row tenant=A — RLS WITH CHECK
    # rejects because the GUC will be set to B but the row's tenant_id will
    # also be B (we always write tenant_id = resolved GUC). So the test must
    # construct the scenario where GUC != row's tenant. We do this by writing
    # via raw SQL with a tenant override.
    import asyncpg
    with pytest.raises(asyncpg.exceptions.PostgresError):
        async with pg_pool.acquire() as conn:
            async with conn.transaction():
                # GUC says A, but try to INSERT a tenant_id=B row.
                await conn.execute(
                    "SELECT set_config('app.tenant_id', 'tenant-a', true)"
                )
                await conn.execute(
                    "INSERT INTO checkpoints "
                    "(run_id, tenant_id, schema_version, status, workflow_class, payload) "
                    "VALUES ($1, $2, $3, $4, $5, $6)",
                    "rls-b", "tenant-b", 1, "paused", "W", b"{}",
                )


@needs_postgres
async def test_rls_select_is_unscoped(pg_pool, fresh_checkpoints_table):
    """D-TENANT-3: SELECT policy USING(true) — scheduler poll sees all tenants."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool, default_workflow_class="W")
    cp_a = _make_checkpoint("select-a")
    cp_b = _make_checkpoint("select-b")
    await store.write(cp_a, tenant_id="tenant-a")
    await store.write(cp_b, tenant_id="tenant-b")

    # No GUC set on this connection — SELECT should still return both rows.
    async with pg_pool.acquire() as conn:
        # Explicitly unset the GUC by entering a fresh txn that resets.
        rows = await conn.fetch(
            "SELECT run_id, tenant_id FROM checkpoints "
            "WHERE run_id IN ('select-a', 'select-b') ORDER BY run_id"
        )
    assert len(rows) == 2
    assert {r["tenant_id"] for r in rows} == {"tenant-a", "tenant-b"}


@needs_postgres
async def test_pool_connection_recycling_does_not_leak_guc(
    pg_pool, fresh_checkpoints_table,
):
    """ADVISOR BLOCKING #1 regression (2026-05-18).

    After a write under tenant A inside a transaction, the connection returns
    to the pool. The next checkout MUST NOT see `current_setting('app.tenant_id')`
    populated. This proves `SET LOCAL` (via set_config(..., true)) confines the
    GUC to the transaction — if we had used bare `SET`, the GUC would leak.
    """
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool, default_workflow_class="W")
    cp = _make_checkpoint("recycle-1")
    await store.write(cp, tenant_id="tenant-a")

    # Re-acquire (likely same physical connection from the pool). Outside any
    # transaction, the GUC must NOT carry tenant-a's value.
    async with pg_pool.acquire() as conn:
        leaked = await conn.fetchval(
            "SELECT current_setting('app.tenant_id', true)"
        )
    # current_setting with missing_ok=true returns empty string when unset.
    assert leaked in ("", None), (
        f"app.tenant_id leaked across pool checkout: {leaked!r}. "
        "SET LOCAL semantics violated — likely a `SET` instead of `SET LOCAL`."
    )


@needs_postgres
async def test_rls_update_rejects_tenant_migration(
    pg_pool, fresh_checkpoints_table,
):
    """RLS UPDATE WITH CHECK rejects an UPDATE that migrates tenant_id."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool, default_workflow_class="W")
    cp = _make_checkpoint("migrate-a")
    await store.write(cp, tenant_id="tenant-a")

    # Try raw UPDATE: GUC=A, but UPDATE sets tenant_id=B. WITH CHECK fails.
    import asyncpg
    with pytest.raises(asyncpg.exceptions.PostgresError):
        async with pg_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute(
                    "SELECT set_config('app.tenant_id', 'tenant-a', true)"
                )
                await conn.execute(
                    "UPDATE checkpoints SET tenant_id = 'tenant-b' "
                    "WHERE run_id = 'migrate-a'"
                )


@needs_postgres
async def test_rls_quarantine_insert_rejects_cross_tenant(
    pg_pool, fresh_checkpoints_table,
):
    """Audit 2026-05-18 Q7 follow-up: quarantine table RLS WITH CHECK rejects
    cross-tenant INSERT (parallel to test_rls_insert_requires_matching_guc
    which covered checkpoints only)."""
    import asyncpg
    with pytest.raises(asyncpg.exceptions.PostgresError):
        async with pg_pool.acquire() as conn:
            async with conn.transaction():
                # GUC says A, INSERT tries to land tenant_id=B.
                await conn.execute(
                    "SELECT set_config('app.tenant_id', 'tenant-a', true)"
                )
                await conn.execute(
                    "INSERT INTO quarantine "
                    "(run_id, tenant_id, failure_count, reason) "
                    "VALUES ($1, $2, $3, $4)",
                    "q-cross", "tenant-b", 3, "manual",
                )


async def test_quarantine_sync_seen_retry_correctness_after_skip():
    """Audit 2026-05-18 Q7 follow-up: when _snapshot_and_insert skips a run
    due to missing tenant_id, it MUST NOT add that run to _seen — otherwise
    the next poll would also skip + the run never gets persisted."""
    from examples.production.durable_postgres.quarantine import QuarantineSync
    from .test_quarantine import _FakeDaemon, _FakePool

    # First poll: no tenant for r1.
    daemon = _FakeDaemon(quarantine={"r1"}, tenants_for_runs={})
    pool = _FakePool()
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]
    await sync._snapshot_and_insert()
    assert "r1" not in sync._seen, "skipped run must not enter _seen"
    assert all("INSERT" not in q for q, _ in pool.conn.executed)

    # Second poll: cache populated; r1 must now INSERT (proves retry works).
    daemon._tenants_for_runs = {"r1": "_default"}
    pool.conn.executed.clear()
    await sync._snapshot_and_insert()
    insert_queries = [q for q, _ in pool.conn.executed if "INSERT INTO quarantine" in q]
    assert len(insert_queries) == 1, "second poll must insert r1 now tenant is known"
    assert "r1" in sync._seen, "after successful INSERT r1 enters _seen"


@needs_postgres
async def test_store_write_with_default_tenant_emits_warning(
    pg_pool, fresh_checkpoints_table, recwarn, monkeypatch,
):
    """D-TENANT-2: writes without tenant context land under _default + warn."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    monkeypatch.delenv("DURABLE_REQUIRE_EXPLICIT_TENANT", raising=False)
    store = PostgresCheckpointStore(pg_pool, default_workflow_class="W")
    cp = _make_checkpoint("default-tenant")

    # No tenant_id kwarg, no ContextVar set.
    await store.write(cp)

    # Row landed under _default tenant.
    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT tenant_id FROM checkpoints WHERE run_id = 'default-tenant'"
        )
    assert row is not None
    assert row["tenant_id"] == RESERVED_DEFAULT_TENANT

    # DeprecationWarning emitted.
    assert any(
        issubclass(w.category, DeprecationWarning)
        and "_default" in str(w.message)
        for w in recwarn
    )
