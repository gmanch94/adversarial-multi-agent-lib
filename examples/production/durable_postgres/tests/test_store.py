"""Unit tests for PostgresCheckpointStore.

Requires POSTGRES_DSN env var. Skipped otherwise.
"""
from __future__ import annotations

from datetime import datetime, timezone, timedelta

import pytest

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    RunNotFound,
)

from examples.production.durable_postgres.tests.conftest import needs_postgres


pytestmark = [pytest.mark.asyncio, needs_postgres]


def _make_checkpoint(run_id: str = "test-run-001", status: str = "paused") -> Checkpoint:
    # v4: workflow_class is NOT a Checkpoint field; it lives on the DB column
    # via the store's default_workflow_class or write_with_class extension.
    return Checkpoint(
        run_id=run_id,
        tenant_id="_default",
        schema_version=1,
        status=status,
        round=1,
        rounds_history=[{"round": 1, "score": 7.5}],
        last_request_json='{"trial_id": "T1"}',
        pause_reason="rolling_data",
        pause_context={"awaiting": "complete labs"},
        budget_used={"tokens_in": 100, "tokens_out": 50, "usd_spent": 0.0042},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T12:00:00Z",
        updated_at="2026-05-16T12:00:00Z",
        wake_at=None,
    )


_TEST_WORKFLOW_CLASS = "x.y.ClinicalTrialEligibilityDurableWorkflow"


async def test_write_then_read_roundtrips(pg_pool, fresh_checkpoints_table):
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint()
    await store.write(cp)
    loaded = await store.read(cp.run_id)
    assert loaded.run_id == cp.run_id
    assert loaded.status == cp.status
    assert loaded.round == cp.round
    assert loaded.last_request_json == cp.last_request_json


async def test_read_missing_raises_run_not_found(pg_pool, fresh_checkpoints_table):
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    with pytest.raises(RunNotFound):
        await store.read("does-not-exist")


async def test_write_is_upsert(pg_pool, fresh_checkpoints_table):
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint()
    await store.write(cp)
    # Second write with same run_id updates, not duplicate-key error
    cp2 = _make_checkpoint()
    object.__setattr__(cp2, "round", 5)
    await store.write(cp2)
    loaded = await store.read(cp.run_id)
    assert loaded.round == 5


async def test_list_paused_filters_by_wake_at(pg_pool, fresh_checkpoints_table):
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)

    now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    past = now - timedelta(hours=1)
    future = now + timedelta(hours=1)

    cp_now_ready = _make_checkpoint(run_id="ready-001")
    object.__setattr__(cp_now_ready, "wake_at", past.isoformat())
    await store.write(cp_now_ready)

    cp_not_ready = _make_checkpoint(run_id="future-002")
    object.__setattr__(cp_not_ready, "wake_at", future.isoformat())
    await store.write(cp_not_ready)

    cp_explicit = _make_checkpoint(run_id="explicit-003")
    object.__setattr__(cp_explicit, "wake_at", None)
    await store.write(cp_explicit)

    tokens = await store.list_paused(wake_before=now)
    ids = {t.run_id for t in tokens}
    # past + None should be returned; future should not
    assert "ready-001" in ids
    assert "explicit-003" in ids
    assert "future-002" not in ids


async def test_delete_idempotent(pg_pool, fresh_checkpoints_table):
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint()
    await store.write(cp)
    await store.delete(cp.run_id)
    # Second delete is no-op
    await store.delete(cp.run_id)
    with pytest.raises(RunNotFound):
        await store.read(cp.run_id)


async def test_run_id_charset_constraint_at_db_layer(pg_pool, fresh_checkpoints_table):
    """Defense in depth: DB rejects bad run_id even if app layer didn't.

    This test inserts via raw SQL (bypassing the store's app-layer regex).
    Demonstrates that the CHECK constraint catches what the regex would miss
    if the app layer ever regressed.
    """
    import asyncpg

    async with pg_pool.acquire() as conn:
        with pytest.raises(asyncpg.exceptions.CheckViolationError):
            await conn.execute(
                """
                INSERT INTO checkpoints
                  (run_id, schema_version, status, workflow_class, payload)
                VALUES ($1, 1, 'paused', 'X', $2)
                """,
                "bad; DROP TABLE checkpoints;",
                b"unused",
            )


async def test_payload_is_bytes_passthrough(pg_pool, fresh_checkpoints_table):
    """Store treats payload as opaque bytes — never parses content."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint()
    # Override the JSON field with bytes-like ciphertext directly
    # (simulates EncryptedCheckpointStore wrapping)
    object.__setattr__(cp, "last_request_json", "ENC:v1:abc123XYZ==")
    await store.write(cp)
    loaded = await store.read(cp.run_id)
    assert loaded.last_request_json == "ENC:v1:abc123XYZ=="


async def test_store_rejects_bad_run_id_before_touching_db(
    pg_pool, fresh_checkpoints_table
):
    """F-H-08: app-layer validation must fire BEFORE asyncpg call.

    Asserts the store raises ValueError (not asyncpg CheckViolationError),
    proving the check happened in Python, not in Postgres.
    """
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    bad_cp = _make_checkpoint(run_id="abc;DROP TABLE")
    with pytest.raises(ValueError, match="invalid run_id"):
        await store.write(bad_cp)
    with pytest.raises(ValueError, match="invalid run_id"):
        await store.read("abc;DROP TABLE")
    with pytest.raises(ValueError, match="invalid run_id"):
        await store.delete("abc;DROP TABLE")


async def test_default_workflow_class_used_for_protocol_write(
    pg_pool, fresh_checkpoints_table
):
    """v4: write(checkpoint) uses default_workflow_class from constructor."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(
        pg_pool, default_workflow_class=_TEST_WORKFLOW_CLASS,
    )
    cp = _make_checkpoint(run_id="wfc-default")
    await store.write(cp)
    async with pg_pool.acquire() as conn:
        wf = await conn.fetchval(
            "SELECT workflow_class FROM checkpoints WHERE run_id = $1",
            "wfc-default",
        )
    assert wf == _TEST_WORKFLOW_CLASS


async def test_write_with_class_overrides_default(pg_pool, fresh_checkpoints_table):
    """v4: write_with_class extension overrides the constructor default."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(
        pg_pool, default_workflow_class="default.class.Name",
    )
    cp = _make_checkpoint(run_id="wfc-override")
    await store.write_with_class(cp, workflow_class="other.class.Name")
    async with pg_pool.acquire() as conn:
        wf = await conn.fetchval(
            "SELECT workflow_class FROM checkpoints WHERE run_id = $1",
            "wfc-override",
        )
    assert wf == "other.class.Name"


async def test_list_paused_returns_tokens_with_workflow_class(
    pg_pool, fresh_checkpoints_table
):
    """v4: list_paused must read workflow_class from the DB column."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(
        pg_pool, default_workflow_class=_TEST_WORKFLOW_CLASS,
    )
    cp = _make_checkpoint(run_id="wfc-list")
    await store.write(cp)
    tokens = await store.list_paused(wake_before=datetime(2099, 1, 1, tzinfo=timezone.utc))
    assert len(tokens) == 1
    assert tokens[0].workflow_class == _TEST_WORKFLOW_CLASS


async def test_workflow_class_too_long_rejected(pg_pool, fresh_checkpoints_table):
    """v4: workflow_class > 512 chars rejected at app layer before DB CHECK."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint(run_id="wfc-toolong")
    too_long = "x." * 300  # 600 chars
    with pytest.raises(ValueError, match="workflow_class exceeds"):
        await store.write_with_class(cp, workflow_class=too_long)


async def test_write_if_unchanged_cas_success(pg_pool, fresh_checkpoints_table):
    """F-H-06: CAS write succeeds when updated_at matches."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint(run_id="cas-001")
    await store.write(cp)

    async with pg_pool.acquire() as conn:
        original_updated_at = await conn.fetchval(
            "SELECT updated_at FROM checkpoints WHERE run_id = $1", "cas-001",
        )

    cp_v2 = _make_checkpoint(run_id="cas-001")
    object.__setattr__(cp_v2, "round", 5)
    await store.write_if_unchanged(cp_v2, expected_updated_at=original_updated_at)

    loaded = await store.read("cas-001")
    assert loaded.round == 5


async def test_write_if_unchanged_cas_failure(pg_pool, fresh_checkpoints_table):
    """F-H-06: CAS write raises when updated_at has moved."""
    from examples.production.durable_postgres.store import (
        PostgresCheckpointStore,
        CompareAndSwapFailed,
    )

    store = PostgresCheckpointStore(pg_pool)
    cp = _make_checkpoint(run_id="cas-002")
    await store.write(cp)

    # Simulate a stale expected_updated_at (1 day in the past)
    from datetime import timedelta
    async with pg_pool.acquire() as conn:
        current = await conn.fetchval(
            "SELECT updated_at FROM checkpoints WHERE run_id = $1", "cas-002",
        )
    stale = current - timedelta(days=1)

    cp_v2 = _make_checkpoint(run_id="cas-002")
    with pytest.raises(CompareAndSwapFailed, match="updated_at moved"):
        await store.write_if_unchanged(cp_v2, expected_updated_at=stale)


async def test_list_paused_limit_capped(pg_pool, fresh_checkpoints_table):
    """list_paused honors the batch_size cap."""
    from examples.production.durable_postgres.store import PostgresCheckpointStore

    store = PostgresCheckpointStore(pg_pool, max_batch=3)
    now = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
    for i in range(5):
        cp = _make_checkpoint(run_id=f"r{i:03d}")
        object.__setattr__(cp, "wake_at", (now - timedelta(minutes=i)).isoformat())
        await store.write(cp)
    tokens = await store.list_paused(wake_before=now)
    assert len(tokens) <= 3
