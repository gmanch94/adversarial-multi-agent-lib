"""Multi-tenant isolation tests (Tier 2.1b / D-TENANT-1..10).

Two test bands:
  - Mocked: charset validation, _validate_tenant_id, Checkpoint.tenant_id
    validation, operator script tenant-flag enforcement. Run on every CI (~ms).
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

Tier 2.1b removed: ContextVar plumbing, `_resolve_tenant_id` fallback chain,
`MissingTenantContext`, `tenant_context`/`reset_tenant_context`. After 2.1b
`Checkpoint.tenant_id` is canonical; tests of those vestigial channels deleted.
"""
from __future__ import annotations

import pytest

from adv_multi_agent.core.durable.checkpoint import Checkpoint
from examples.production.durable_postgres.store import (
    RESERVED_DEFAULT_TENANT,
    _TENANT_ID_RE,
    _validate_tenant_id,
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


def test_validate_tenant_id_passes_valid():
    assert _validate_tenant_id("tenant-a") == "tenant-a"
    assert _validate_tenant_id(RESERVED_DEFAULT_TENANT) == RESERVED_DEFAULT_TENANT


def test_validate_tenant_id_raises_on_invalid():
    with pytest.raises(ValueError, match="invalid tenant_id"):
        _validate_tenant_id("has space")
    with pytest.raises(ValueError, match="invalid tenant_id"):
        _validate_tenant_id("tenant;DROP")


def test_checkpoint_rejects_invalid_tenant_id():
    """D-TENANT-1: Checkpoint.__post_init__ raises on bad tenant_id."""
    with pytest.raises(ValueError, match="tenant_id must match"):
        Checkpoint(
            run_id="run-1",
            tenant_id="has space",  # invalid charset
            schema_version=1, status="paused", round=0,
            rounds_history=[], last_request_json="{}",
            pause_reason=None, pause_context={},
            budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
            pinned_executor_model="claude-opus-4-7",
            pinned_reviewer_model="gpt-4o",
            created_at="2026-05-18T00:00:00+00:00",
            updated_at="2026-05-18T00:00:00+00:00",
        )


def test_checkpoint_requires_tenant_id():
    """D-TENANT-1: Checkpoint without tenant_id raises TypeError."""
    with pytest.raises(TypeError, match="tenant_id"):
        Checkpoint(  # type: ignore[call-arg]
            run_id="run-1",
            schema_version=1, status="paused", round=0,
            rounds_history=[], last_request_json="{}",
            pause_reason=None, pause_context={},
            budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
            pinned_executor_model="claude-opus-4-7",
            pinned_reviewer_model="gpt-4o",
            created_at="2026-05-18T00:00:00+00:00",
            updated_at="2026-05-18T00:00:00+00:00",
        )


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

def _make_checkpoint(run_id: str, tenant_id: str = "_default") -> Checkpoint:
    """Minimal valid Checkpoint for store.write tests."""
    return Checkpoint(
        run_id=run_id,
        tenant_id=tenant_id,
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
async def test_rls_insert_requires_matching_guc(nonsuper_pool, fresh_checkpoints_table):
    """RLS INSERT policy rejects rows whose tenant_id != current_setting GUC.

    Runs on a provisioned NOSUPERUSER pool — superusers bypass RLS by design, so
    the throwaway image's superuser role can't exercise this. The same-tenant
    write below is the POSITIVE CONTROL: it proves the cross-tenant rejection is
    RLS (WITH CHECK), not a missing INSERT grant — both surface as 42501.
    """
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(nonsuper_pool, default_workflow_class="W")

    # Positive control: same-tenant write succeeds under the non-super role
    # (GUC=A, row=A). If the INSERT grant were missing, THIS would fail too.
    await store.write(_make_checkpoint("rls-a", tenant_id="tenant-a"))

    # Negative: GUC says A, but INSERT a tenant_id=B row — RLS WITH CHECK rejects.
    import asyncpg
    with pytest.raises(asyncpg.exceptions.PostgresError):
        async with nonsuper_pool.acquire() as conn:
            async with conn.transaction():
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
    cp_a = _make_checkpoint("select-a", tenant_id="tenant-a")
    cp_b = _make_checkpoint("select-b", tenant_id="tenant-b")
    await store.write(cp_a)
    await store.write(cp_b)

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
    cp = _make_checkpoint("recycle-1", tenant_id="tenant-a")
    await store.write(cp)

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
    nonsuper_pool, fresh_checkpoints_table,
):
    """RLS UPDATE WITH CHECK rejects an UPDATE that migrates tenant_id.

    NOSUPERUSER pool (RLS binds only against a non-super role). The seed write
    below is the POSITIVE CONTROL — a same-tenant write succeeding proves the
    migration UPDATE is rejected by RLS, not by a missing UPDATE/INSERT grant.
    """
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(nonsuper_pool, default_workflow_class="W")
    # Positive control: same-tenant seed succeeds under the non-super role.
    await store.write(_make_checkpoint("migrate-a", tenant_id="tenant-a"))

    # Negative: GUC=A, but UPDATE sets tenant_id=B. WITH CHECK fails.
    import asyncpg
    with pytest.raises(asyncpg.exceptions.PostgresError):
        async with nonsuper_pool.acquire() as conn:
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
    nonsuper_pool, fresh_checkpoints_table,
):
    """Audit 2026-05-18 Q7 follow-up: quarantine table RLS WITH CHECK rejects
    cross-tenant INSERT (parallel to test_rls_insert_requires_matching_guc
    which covered checkpoints only).

    NOSUPERUSER pool. The same-tenant INSERT below is the POSITIVE CONTROL —
    proving the cross-tenant rejection is RLS, not a missing quarantine grant.
    """
    import asyncpg
    # Positive control: GUC=B, row=B — succeeds under the non-super role.
    async with nonsuper_pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute(
                "SELECT set_config('app.tenant_id', 'tenant-b', true)"
            )
            await conn.execute(
                "INSERT INTO quarantine "
                "(run_id, tenant_id, failure_count, reason) "
                "VALUES ($1, $2, $3, $4)",
                "q-ok", "tenant-b", 3, "manual",
            )

    # Negative: GUC says A, INSERT tries to land tenant_id=B — RLS rejects.
    with pytest.raises(asyncpg.exceptions.PostgresError):
        async with nonsuper_pool.acquire() as conn:
            async with conn.transaction():
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
    due to missing checkpoint row, it MUST NOT add that run to _seen —
    otherwise the next poll would also skip + the run never gets persisted.

    Tier 2.1b: tenant_id is looked up via SELECT, not from cache. First poll
    simulates the checkpoint-not-yet-present state; second poll has the row."""
    from examples.production.durable_postgres.quarantine import QuarantineSync
    from .test_quarantine import _FakeDaemon, _FakePool

    # First poll: SELECT returns None (no checkpoint row yet).
    daemon = _FakeDaemon(quarantine={"r1"})
    pool = _FakePool()
    pool.conn.fetch_rows = []  # SELECT tenant_id returns None
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]
    await sync._snapshot_and_insert()
    assert "r1" not in sync._seen, "skipped run must not enter _seen"
    assert all("INSERT" not in q for q, _ in pool.conn.executed)

    # Second poll: SELECT returns a row; r1 must now INSERT (proves retry works).
    pool.conn.fetch_rows = [{"tenant_id": "_default"}]
    pool.conn.executed.clear()
    await sync._snapshot_and_insert()
    insert_queries = [q for q, _ in pool.conn.executed if "INSERT INTO quarantine" in q]
    assert len(insert_queries) == 1, "second poll must insert r1 now tenant is known"
    assert "r1" in sync._seen, "after successful INSERT r1 enters _seen"


@needs_postgres
async def test_read_after_write_preserves_tenant_id(
    pg_pool, fresh_checkpoints_table,
):
    """Audit 2026-05-18 Q8 follow-up: write→read roundtrip preserves
    `Checkpoint.tenant_id`. This is the resume-path correctness invariant —
    if tenant_id drifts across persistence, the next `store.write(cp)`
    SET LOCAL would target the wrong tenant + RLS would reject."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool, default_workflow_class="W")
    cp_written = _make_checkpoint("roundtrip-1", tenant_id="tenant-x")
    await store.write(cp_written)

    cp_read = await store.read("roundtrip-1")
    assert cp_read.tenant_id == "tenant-x"
    assert cp_read.tenant_id == cp_written.tenant_id


@needs_postgres
async def test_delete_with_wrong_tenant_raises_run_not_found(
    nonsuper_pool, fresh_checkpoints_table,
):
    """Audit 2026-05-18 Q6 follow-up: delete() with mismatched tenant_id
    no longer silently affects 0 rows — it raises RunNotFound so operators
    get a signal when their --tenant flag is wrong.

    NOSUPERUSER pool so the RLS DELETE policy actually hides the row (superusers
    bypass it). The right-tenant delete succeeding is the POSITIVE CONTROL —
    proving the wrong-tenant RunNotFound came from RLS, not a missing row/grant.
    """
    from adv_multi_agent.core.durable.checkpoint import RunNotFound
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(nonsuper_pool, default_workflow_class="W")
    await store.write(_make_checkpoint("delete-1", tenant_id="tenant-real"))

    # Wrong tenant — RLS hides the row from DELETE. delete() now raises.
    with pytest.raises(RunNotFound, match="tenant_id mismatch"):
        await store.delete("delete-1", tenant_id="tenant-wrong")

    # Positive control: right tenant succeeds (proves the row existed + grant OK).
    await store.delete("delete-1", tenant_id="tenant-real")


@needs_postgres
async def test_store_write_with_default_tenant_lands_under_default(
    pg_pool, fresh_checkpoints_table,
):
    """D-TENANT-2 (Tier 2.1b): single-tenant deployment passes
    `tenant_id="_default"` on the Checkpoint; row lands under that tenant.

    The 2.1a DeprecationWarning fallback path is removed in 2.1b — callers
    MUST construct Checkpoint with an explicit tenant_id. `_default` is the
    reserved name for single-tenant operators.
    """
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool, default_workflow_class="W")
    cp = _make_checkpoint("default-tenant", tenant_id=RESERVED_DEFAULT_TENANT)
    await store.write(cp)

    async with pg_pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT tenant_id FROM checkpoints WHERE run_id = 'default-tenant'"
        )
    assert row is not None
    assert row["tenant_id"] == RESERVED_DEFAULT_TENANT
