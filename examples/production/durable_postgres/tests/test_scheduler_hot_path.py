"""Tier 1.4 (EVE follow-up) — PollingScheduler + SchedulerDaemon hot-path tests
against a live Postgres.

Library-level unit tests for the scheduler use a `FakeCheckpointStore`. These
tests run the same `PollingScheduler` + `SchedulerDaemon` against the
reference deployment's real `PostgresCheckpointStore`, exercising:

  - poll_ready SQL semantics (status filter, wake_at filter, ORDER BY,
    batch_size limit)
  - SchedulerDaemon round-loop iteration against live tokens
  - Quarantine accumulation under repeated CheckpointCorrupt
  - Token-resolver hook fires on each poll batch
  - Stop semantics — daemon exits on .stop() within one poll interval

Requires `POSTGRES_DSN` (auto-skip via `needs_postgres`). Reuses the
fresh_checkpoints_table fixture so each test starts from a clean schema.

Naming convention: every run_id prefixed `sch-` so a partial test leak is
easy to distinguish from `t1-`, `t3-`, etc. used by smoke_test.py.
"""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from typing import Any

import pytest

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    CheckpointCorrupt,
)
from adv_multi_agent.core.durable.scheduler import (
    PollingScheduler,
    SchedulerDaemon,
)
from adv_multi_agent.core.durable.token import ResumeToken

from examples.production.durable_postgres.store import PostgresCheckpointStore
from examples.production.durable_postgres.tests.conftest import needs_postgres


pytestmark = [pytest.mark.asyncio, needs_postgres]


_HOT_WORKFLOW_CLASS = "x.Y.HotPathTestWorkflow"


def _cp(
    run_id: str,
    status: str = "paused",
    wake_at: datetime | None = None,
) -> Checkpoint:
    wake_at_iso = wake_at.isoformat() if wake_at is not None else None
    now = datetime.now(timezone.utc).isoformat()
    return Checkpoint(
        run_id=run_id,
        schema_version=1,
        status=status,
        round=1,
        rounds_history=[{"round": 1}],
        last_request_json='{"hot": true}',
        pause_reason="rolling_data",
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        wake_at=wake_at_iso,
        created_at=now,
        updated_at=now,
    )


def _make_store(pg_pool: Any) -> PostgresCheckpointStore:
    return PostgresCheckpointStore(
        pg_pool, default_workflow_class=_HOT_WORKFLOW_CLASS,
    )


# ---------------------------------------------------------------------------
# PollingScheduler.poll_ready — SQL semantics
# ---------------------------------------------------------------------------


async def test_poll_ready_returns_paused_with_null_wake_at(
    pg_pool, fresh_checkpoints_table,
):
    store = _make_store(pg_pool)
    await store.write(_cp("sch-null-1"))
    await store.write(_cp("sch-null-2"))
    sched = PollingScheduler(store)
    tokens = await sched.poll_ready(batch_size=10)
    assert {t.run_id for t in tokens} == {"sch-null-1", "sch-null-2"}


async def test_poll_ready_filters_status_running(
    pg_pool, fresh_checkpoints_table,
):
    store = _make_store(pg_pool)
    await store.write(_cp("sch-run", status="running"))
    await store.write(_cp("sch-paused"))
    sched = PollingScheduler(store)
    tokens = await sched.poll_ready(batch_size=10)
    assert [t.run_id for t in tokens] == ["sch-paused"]


async def test_poll_ready_filters_future_wake_at(
    pg_pool, fresh_checkpoints_table,
):
    store = _make_store(pg_pool)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    future = datetime.now(timezone.utc) + timedelta(hours=1)
    await store.write(_cp("sch-past", wake_at=past))
    await store.write(_cp("sch-future", wake_at=future))
    sched = PollingScheduler(store)
    tokens = await sched.poll_ready(batch_size=10)
    assert [t.run_id for t in tokens] == ["sch-past"]


async def test_poll_ready_orders_nulls_first(pg_pool, fresh_checkpoints_table):
    """ORDER BY wake_at NULLS FIRST in store.list_paused.

    Explicit-resume rows (wake_at IS NULL) should be drained ahead of
    time-driven rows so a stuck scheduler doesn't starve the explicit queue.
    """
    store = _make_store(pg_pool)
    past = datetime.now(timezone.utc) - timedelta(minutes=5)
    await store.write(_cp("sch-timed-1", wake_at=past))
    await store.write(_cp("sch-explicit-1"))
    await store.write(_cp("sch-timed-2", wake_at=past - timedelta(minutes=1)))
    await store.write(_cp("sch-explicit-2"))
    sched = PollingScheduler(store)
    tokens = await sched.poll_ready(batch_size=10)
    # First two must be the NULL-wake_at rows (ordering within that group
    # is unspecified — assert as a set).
    assert {t.run_id for t in tokens[:2]} == {"sch-explicit-1", "sch-explicit-2"}
    assert {t.run_id for t in tokens[2:]} == {"sch-timed-1", "sch-timed-2"}


async def test_poll_ready_honors_batch_size(pg_pool, fresh_checkpoints_table):
    store = _make_store(pg_pool)
    for i in range(20):
        await store.write(_cp(f"sch-batch-{i:02d}"))
    sched = PollingScheduler(store)
    tokens = await sched.poll_ready(batch_size=5)
    assert len(tokens) == 5


async def test_poll_ready_empty_when_no_paused(pg_pool, fresh_checkpoints_table):
    sched = PollingScheduler(_make_store(pg_pool))
    tokens = await sched.poll_ready(batch_size=10)
    assert tokens == []


# ---------------------------------------------------------------------------
# SchedulerDaemon round-loop against live store
# ---------------------------------------------------------------------------


class _FakeDurableWorkflow:
    """Stand-in for DurableWorkflow with a configurable resume side-effect."""
    def __init__(self, side_effect: Exception | None = None) -> None:
        self.resume_calls: list[ResumeToken] = []
        self._side_effect = side_effect

    async def resume(self, token: ResumeToken) -> None:
        self.resume_calls.append(token)
        if self._side_effect is not None:
            raise self._side_effect


async def test_daemon_resumes_ready_runs_then_stops(
    pg_pool, fresh_checkpoints_table,
):
    store = _make_store(pg_pool)
    await store.write(_cp("sch-d-1"))
    await store.write(_cp("sch-d-2"))

    fake_wf = _FakeDurableWorkflow()
    sched = PollingScheduler(store)
    daemon = SchedulerDaemon(
        scheduler=sched,
        workflow_factory=lambda wc: fake_wf,  # type: ignore[arg-type]
        poll_interval_seconds=0.05,
        batch_size=10,
    )
    task = asyncio.create_task(daemon.run_forever())
    await asyncio.sleep(0.2)
    daemon.stop()
    await asyncio.wait_for(task, timeout=2.0)

    resumed = {t.run_id for t in fake_wf.resume_calls}
    assert resumed >= {"sch-d-1", "sch-d-2"}


async def test_daemon_quarantines_after_max_retries(
    pg_pool, fresh_checkpoints_table,
):
    store = _make_store(pg_pool)
    await store.write(_cp("sch-q-1"))

    fake_wf = _FakeDurableWorkflow(side_effect=CheckpointCorrupt("synthetic"))
    sched = PollingScheduler(store)
    daemon = SchedulerDaemon(
        scheduler=sched,
        workflow_factory=lambda wc: fake_wf,  # type: ignore[arg-type]
        poll_interval_seconds=0.05,
        batch_size=10,
        max_retries=3,
    )
    task = asyncio.create_task(daemon.run_forever())
    await asyncio.sleep(0.4)
    daemon.stop()
    await asyncio.wait_for(task, timeout=2.0)

    assert "sch-q-1" in daemon._quarantine
    # After quarantine, subsequent polls SKIP the token (no resume call growth).
    pre_qcount = len(fake_wf.resume_calls)
    await asyncio.sleep(0.15)
    assert len(fake_wf.resume_calls) == pre_qcount


async def test_daemon_clears_failure_counter_on_success(
    pg_pool, fresh_checkpoints_table,
):
    store = _make_store(pg_pool)
    await store.write(_cp("sch-recover"))

    # Resume fails twice then succeeds; failure counter should reset.
    call_count = {"n": 0}

    class _FlakyWf:
        def __init__(self) -> None:
            self.resume_calls: list[ResumeToken] = []

        async def resume(self, token: ResumeToken) -> None:
            self.resume_calls.append(token)
            call_count["n"] += 1
            if call_count["n"] <= 2:
                raise CheckpointCorrupt("synthetic-flake")

    flaky = _FlakyWf()
    sched = PollingScheduler(store)
    daemon = SchedulerDaemon(
        scheduler=sched,
        workflow_factory=lambda wc: flaky,  # type: ignore[arg-type]
        poll_interval_seconds=0.05,
        batch_size=10,
        max_retries=5,
    )
    task = asyncio.create_task(daemon.run_forever())
    await asyncio.sleep(0.3)
    daemon.stop()
    await asyncio.wait_for(task, timeout=2.0)

    assert "sch-recover" not in daemon._quarantine
    assert "sch-recover" not in daemon._failures


async def test_daemon_token_resolver_hook_fires(
    pg_pool, fresh_checkpoints_table,
):
    store = _make_store(pg_pool)
    await store.write(_cp("sch-resolver"))

    resolved: list[str] = []

    def _resolver(token: ResumeToken) -> ResumeToken:
        resolved.append(token.run_id)
        return token

    fake_wf = _FakeDurableWorkflow()
    sched = PollingScheduler(store)
    daemon = SchedulerDaemon(
        scheduler=sched,
        workflow_factory=lambda wc: fake_wf,  # type: ignore[arg-type]
        token_resolver=_resolver,
        poll_interval_seconds=0.05,
        batch_size=10,
    )
    task = asyncio.create_task(daemon.run_forever())
    await asyncio.sleep(0.15)
    daemon.stop()
    await asyncio.wait_for(task, timeout=2.0)

    assert "sch-resolver" in resolved


async def test_daemon_stop_returns_within_one_poll_interval(
    pg_pool, fresh_checkpoints_table,
):
    sched = PollingScheduler(_make_store(pg_pool))
    daemon = SchedulerDaemon(
        scheduler=sched,
        workflow_factory=lambda wc: _FakeDurableWorkflow(),  # type: ignore[arg-type]
        poll_interval_seconds=2.0,
    )
    task = asyncio.create_task(daemon.run_forever())
    await asyncio.sleep(0.1)
    daemon.stop()
    start = asyncio.get_event_loop().time()
    await asyncio.wait_for(task, timeout=3.0)
    elapsed = asyncio.get_event_loop().time() - start
    # stop() signals the event; run_forever's `await self._stop.wait()`
    # returns immediately. Bound the assertion generously.
    assert elapsed < 1.0


# ---------------------------------------------------------------------------
# Throughput sanity (informational, not a benchmark)
# ---------------------------------------------------------------------------


async def test_poll_ready_at_100_paused_under_1s(
    pg_pool, fresh_checkpoints_table,
):
    """Sanity floor: list_paused over 100 rows returns in <1s on any reasonable
    Postgres. Catches a runaway query plan regression (e.g. missing partial
    index) before it becomes an operator issue.
    """
    store = _make_store(pg_pool)
    for i in range(100):
        await store.write(_cp(f"sch-thr-{i:03d}"))
    sched = PollingScheduler(store)
    loop = asyncio.get_event_loop()
    t0 = loop.time()
    tokens = await sched.poll_ready(batch_size=100)
    elapsed = loop.time() - t0
    assert len(tokens) == 100
    assert elapsed < 1.0, f"poll_ready 100 rows took {elapsed:.3f}s, expected <1s"
