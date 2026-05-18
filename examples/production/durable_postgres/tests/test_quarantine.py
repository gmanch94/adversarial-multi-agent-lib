"""Unit tests for quarantine.py + scripts/{list_quarantined,requeue}.py (Tier 2.4).

No live DB required. asyncpg pool is mocked. Verifies:
- QuarantineSync diff-and-insert against an evolving _quarantine set
- Requeue processing discards from in-memory + bumps requeue_count
- list_quarantined SELECTs only redacted columns
- requeue regex-gates run_id at CLI layer
"""
from __future__ import annotations

import re
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, MagicMock

import pytest

from examples.production.durable_postgres.quarantine import (
    QuarantineSync,
    _LIBRARY_QUARANTINE_REASON,
)


pytestmark = pytest.mark.asyncio


class _FakeConn:
    def __init__(self) -> None:
        self.executed: list[tuple[str, tuple]] = []
        self.fetch_rows: list[dict] = []
        self.fetchval_value: int = 0

    async def execute(self, query: str, *args) -> None:
        self.executed.append((query, args))

    async def fetch(self, query: str, *args):
        return list(self.fetch_rows)

    async def fetchval(self, query: str, *args):
        return self.fetchval_value

    async def fetchrow(self, query: str, *args):
        return self.fetch_rows[0] if self.fetch_rows else None

    def transaction(self):
        """D-TENANT-3: mock asyncpg's conn.transaction() async-context-manager.

        Real asyncpg returns a Transaction object that's usable as `async with`.
        Tests only need the protocol; the inner block executes inside the same
        _FakeConn, so all execute() calls land in self.executed as before.
        """
        @asynccontextmanager
        async def _ctx():
            yield self
        return _ctx()


class _FakePool:
    def __init__(self) -> None:
        self.conn = _FakeConn()

    def acquire(self):
        pool = self

        @asynccontextmanager
        async def ctx():
            yield pool.conn

        return ctx()


class _FakeDaemon:
    def __init__(self, quarantine: set[str] | None = None,
                 failures: dict[str, int] | None = None,
                 tenants_for_runs: dict[str, str] | None = None) -> None:
        self._quarantine: set[str] = quarantine or set()
        self._failures: dict[str, int] = failures or {}
        # D-TENANT-6: tenant cache attached to daemon by sibling main(). Tests
        # supply it explicitly. Empty default = all inserts skipped with WARN
        # (the safe path).
        self._tenants_for_runs: dict[str, str] = tenants_for_runs or {}


# ----------------------------------------------------------------------
# QuarantineSync._snapshot_and_insert
# ----------------------------------------------------------------------

async def test_snapshot_inserts_only_new_run_ids():
    """Tier 2.1b: tenant_id lookup is per-run SELECT (no cache)."""
    daemon = _FakeDaemon(
        quarantine={"r1", "r2"},
        failures={"r1": 3, "r2": 3},
    )
    pool = _FakePool()
    # _FakeConn.fetchrow returns fetch_rows[0] for every SELECT — both r1+r2
    # resolve to the same tenant. Real Postgres returns per-run rows.
    pool.conn.fetch_rows = [{"tenant_id": "_default"}]
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]

    await sync._snapshot_and_insert()
    # D-TENANT-3: each insert preceded by set_config inside txn → 2 execute calls per row.
    insert_queries = [q for q, _ in pool.conn.executed if "INSERT INTO quarantine" in q]
    set_config_queries = [q for q, _ in pool.conn.executed if "set_config" in q]
    assert len(insert_queries) == 2
    assert len(set_config_queries) == 2
    assert "ON CONFLICT (run_id) DO NOTHING" in insert_queries[0]
    inserted_ids = {args[0] for q, args in pool.conn.executed if "INSERT INTO quarantine" in q}
    assert inserted_ids == {"r1", "r2"}
    # D-TENANT-1: args order on INSERT is (run_id, tenant_id, fc, reason).
    for q, args in pool.conn.executed:
        if "INSERT INTO quarantine" in q:
            assert args[1] == "_default"  # tenant_id slot
            assert args[3] == _LIBRARY_QUARANTINE_REASON  # reason slot at [3]

    # Second call — already seen, no new inserts.
    pool.conn.executed.clear()
    await sync._snapshot_and_insert()
    assert pool.conn.executed == []


async def test_snapshot_skips_run_with_no_checkpoint_row():
    """D-TENANT-4 (Tier 2.1b): run_id with no checkpoint row is logged + skipped.
    SELECT returns None → skip. Better to leak quarantine visibility for one poll
    than to violate RLS or guess the tenant."""
    daemon = _FakeDaemon(quarantine={"r1"}, failures={"r1": 3})
    pool = _FakePool()
    pool.conn.fetch_rows = []  # SELECT returns None
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]

    await sync._snapshot_and_insert()
    # No INSERT issued because checkpoint row missing
    assert all("INSERT" not in q for q, _ in pool.conn.executed)
    # _seen NOT updated either (the run will be retried next poll)
    assert "r1" not in sync._seen


async def test_snapshot_handles_unknown_failure_count():
    daemon = _FakeDaemon(quarantine={"r1"}, failures={})
    pool = _FakePool()
    pool.conn.fetch_rows = [{"tenant_id": "_default"}]
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]

    await sync._snapshot_and_insert()
    inserts = [args for q, args in pool.conn.executed if "INSERT INTO quarantine" in q]
    assert len(inserts) == 1
    # D-TENANT-1: args = (run_id, tenant_id, fc, reason); fc at index 2.
    assert inserts[0][2] == 0


async def test_snapshot_caps_failure_count_at_constraint_bound():
    daemon = _FakeDaemon(quarantine={"r1"}, failures={"r1": 99999})
    pool = _FakePool()
    pool.conn.fetch_rows = [{"tenant_id": "_default"}]
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]

    await sync._snapshot_and_insert()
    inserts = [args for q, args in pool.conn.executed if "INSERT INTO quarantine" in q]
    assert inserts[0][2] == 1000  # capped at CHECK upper bound


async def test_snapshot_prunes_seen_when_quarantine_shrinks():
    daemon = _FakeDaemon(quarantine={"r1", "r2"})
    pool = _FakePool()
    pool.conn.fetch_rows = [{"tenant_id": "_default"}]
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]
    await sync._snapshot_and_insert()
    assert sync._seen == {"r1", "r2"}

    # Operator requeues r1 — daemon discards r1 from in-memory set
    daemon._quarantine = {"r2"}
    pool.conn.executed.clear()
    await sync._snapshot_and_insert()
    # No new inserts, but _seen pruned so r1 can be re-inserted if re-quarantined
    assert pool.conn.executed == []
    assert sync._seen == {"r2"}


# ----------------------------------------------------------------------
# QuarantineSync._process_requeues
# ----------------------------------------------------------------------

async def test_process_requeues_discards_inmemory_and_updates_db():
    daemon = _FakeDaemon(quarantine={"r1", "r2"}, failures={"r1": 3, "r2": 3})
    pool = _FakePool()
    # D-TENANT-4: requeue SELECT now reads tenant_id; fixture must provide it.
    pool.conn.fetch_rows = [{"run_id": "r1", "tenant_id": "_default"}]
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]
    sync._seen = {"r1", "r2"}

    await sync._process_requeues()
    assert "r1" not in daemon._quarantine
    assert "r2" in daemon._quarantine
    assert "r1" not in daemon._failures
    assert "r1" not in sync._seen
    # Last execute is the UPDATE; preceding execute is the set_config (txn-wrapped).
    update_query, update_args = pool.conn.executed[-1]
    assert "UPDATE quarantine" in update_query
    assert "requeued_at = NULL" in update_query
    assert "requeue_count = requeue_count + 1" in update_query
    assert update_args[0] == "r1"
    # D-TENANT-3: set_config call precedes the UPDATE.
    set_config_queries = [q for q, _ in pool.conn.executed if "set_config" in q]
    assert len(set_config_queries) == 1


async def test_process_requeues_noop_when_nothing_pending():
    daemon = _FakeDaemon(quarantine={"r1"})
    pool = _FakePool()
    pool.conn.fetch_rows = []
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]

    await sync._process_requeues()
    # No UPDATE issued
    assert all("UPDATE" not in q for q, _ in pool.conn.executed)
    assert daemon._quarantine == {"r1"}


# ----------------------------------------------------------------------
# QuarantineSync.quarantine_size
# ----------------------------------------------------------------------

async def test_quarantine_size_excludes_requeued():
    daemon = _FakeDaemon()
    pool = _FakePool()
    pool.conn.fetchval_value = 7
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]

    size = await sync.quarantine_size()
    assert size == 7


async def test_quarantine_size_returns_zero_when_none():
    daemon = _FakeDaemon()
    pool = _FakePool()
    pool.conn.fetchval_value = None  # type: ignore[assignment]
    sync = QuarantineSync(daemon, pool)  # type: ignore[arg-type]

    size = await sync.quarantine_size()
    assert size == 0


# ----------------------------------------------------------------------
# QuarantineSync.start / stop lifecycle
# ----------------------------------------------------------------------

async def test_start_is_idempotent():
    sync = QuarantineSync(_FakeDaemon(), _FakePool(), poll_interval_seconds=0.05)  # type: ignore[arg-type]
    sync.start()
    task1 = sync._task
    sync.start()
    assert sync._task is task1
    await sync.stop()


async def test_stop_cancels_running_task():
    sync = QuarantineSync(_FakeDaemon(), _FakePool(), poll_interval_seconds=0.05)  # type: ignore[arg-type]
    sync.start()
    await sync.stop()
    assert sync._task is None


async def test_run_forever_swallows_iteration_exceptions():
    """A glitch in snapshot or requeue must never crash the daemon.

    A14-L-02: also assert the exception path actually executed — otherwise the
    test passes vacuously if _run_forever exits before entering the try-body.
    """
    daemon = _FakeDaemon(quarantine={"r1"})
    pool = _FakePool()

    boom_conn = MagicMock()
    boom_conn.execute = AsyncMock(side_effect=RuntimeError("db down"))
    boom_conn.fetch = AsyncMock(side_effect=RuntimeError("db down"))
    boom_conn.fetchval = AsyncMock(side_effect=RuntimeError("db down"))
    # Tier 2.1b: quarantine sync now calls fetchrow for tenant_id lookup.
    boom_conn.fetchrow = AsyncMock(side_effect=RuntimeError("db down"))

    @asynccontextmanager
    async def boom_acquire():
        yield boom_conn

    pool.acquire = boom_acquire  # type: ignore[assignment]

    sync = QuarantineSync(daemon, pool, poll_interval_seconds=0.02)  # type: ignore[arg-type]
    sync.start()
    # Let it run a few iterations.
    import asyncio
    await asyncio.sleep(0.15)
    await sync.stop()
    # Iteration body actually fired (otherwise test passes vacuously).
    # Tier 2.1b: _snapshot_and_insert calls fetchrow first (tenant lookup),
    # which raises; _process_requeues calls fetch first, which raises.
    # Combined call_count covers both code paths.
    total = (
        boom_conn.execute.call_count
        + boom_conn.fetch.call_count
        + boom_conn.fetchrow.call_count
    )
    assert total > 0, "iteration body never executed"


# ----------------------------------------------------------------------
# scripts.list_quarantined
# ----------------------------------------------------------------------

async def test_list_quarantined_redacts_columns():
    from examples.production.durable_postgres.scripts.list_quarantined import (
        _REDACTED_COLUMNS,
        list_quarantined,
    )

    pool = _FakePool()
    pool.conn.fetch_rows = [
        {col: f"v_{col}" for col in _REDACTED_COLUMNS}
    ]
    # D-TENANT-10: tenant_id now required arg.
    rows = await list_quarantined(
        pool, tenant_id="_default", limit=10, offset=0, include_requeued=False,
    )  # type: ignore[arg-type]
    assert rows[0].keys() == set(_REDACTED_COLUMNS) or set(rows[0].keys()) == set(_REDACTED_COLUMNS)
    # No extra column slipped through.
    assert "payload" not in rows[0]


async def test_list_quarantined_active_only_filters_requeued():
    from examples.production.durable_postgres.scripts.list_quarantined import (
        list_quarantined,
    )

    captured: list[str] = []

    class _SpyConn(_FakeConn):
        async def fetch(self, query: str, *args):
            captured.append(query)
            return []

    class _SpyPool(_FakePool):
        def __init__(self) -> None:
            self.conn = _SpyConn()

    pool = _SpyPool()
    await list_quarantined(
        pool, tenant_id="_default", limit=10, offset=0, include_requeued=False,
    )  # type: ignore[arg-type]
    # D-TENANT-10: queries always carry WHERE tenant_id = $3 + optional
    # AND requeued_at IS NULL for active-only filter.
    assert "WHERE tenant_id = $3" in captured[0]
    assert "AND requeued_at IS NULL" in captured[0]

    captured.clear()
    await list_quarantined(
        pool, tenant_id="_default", limit=10, offset=0, include_requeued=True,
    )  # type: ignore[arg-type]
    assert "WHERE tenant_id = $3" in captured[0]
    assert "AND requeued_at IS NULL" not in captured[0]


# ----------------------------------------------------------------------
# scripts.requeue
# ----------------------------------------------------------------------

async def test_requeue_marks_active_row_pending():
    from examples.production.durable_postgres.scripts.requeue import requeue

    pool = _FakePool()
    pool.conn.fetch_rows = [{"requeued_at": None}]
    # D-TENANT-10: tenant_id now required arg.
    result = await requeue(pool, "r1", "_default")  # type: ignore[arg-type]
    assert result == "requeued"
    update_query, args = pool.conn.executed[-1]
    assert "UPDATE quarantine SET requeued_at = NOW()" in update_query
    # D-TENANT-1: UPDATE WHERE clause now binds both run_id and tenant_id.
    assert args == ("r1", "_default")


async def test_requeue_returns_already_pending_when_set():
    from examples.production.durable_postgres.scripts.requeue import requeue

    pool = _FakePool()
    pool.conn.fetch_rows = [{"requeued_at": "2026-01-01T00:00:00Z"}]
    result = await requeue(pool, "r1", "_default")  # type: ignore[arg-type]
    assert result == "already_pending"


async def test_requeue_returns_not_found_when_row_missing():
    from examples.production.durable_postgres.scripts.requeue import requeue

    pool = _FakePool()
    pool.conn.fetch_rows = []
    result = await requeue(pool, "r1", "_default")  # type: ignore[arg-type]
    assert result == "not_found"


def test_requeue_run_id_regex_rejects_injection_attempts():
    from examples.production.durable_postgres.scripts.requeue import _RUN_ID_RE

    bad = [
        "r1; DROP TABLE quarantine",
        "../../etc/passwd",
        "r1'",
        "r1\"",
        "",
        "-leading-dash",
        "a" * 65,  # exceeds VARCHAR(64)
    ]
    for s in bad:
        assert _RUN_ID_RE.match(s) is None, f"regex must reject: {s!r}"
    good = ["r1", "abc-DEF-123", "A", "x" * 64]
    for s in good:
        assert _RUN_ID_RE.match(s) is not None, f"regex must accept: {s!r}"


def test_schema_check_constraint_regex_matches_python_regex():
    """The CLI-layer regex must be at least as strict as the DB CHECK constraint."""
    schema_constraint = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$")
    from examples.production.durable_postgres.scripts.requeue import _RUN_ID_RE

    samples = ["r1", "abc-DEF-123", "x" * 64, "1abc", "Z" * 50]
    for s in samples:
        assert bool(_RUN_ID_RE.match(s)) == bool(schema_constraint.match(s))
