"""SchedulerBackend + PollingScheduler + SchedulerDaemon."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from adv_multi_agent.core.durable.checkpoint import (
    Checkpoint,
    MemoryCheckpointStore,
)
from adv_multi_agent.core.durable.scheduler import (
    PollingScheduler,
    SchedulerDaemon,
)
from adv_multi_agent.core.durable.token import CURRENT_SCHEMA_VERSION, ResumeToken
from adv_multi_agent.core.durable.workflow import DurableWorkflow

from .fakes import ToyPausingWorkflow, make_test_config


def make_paused_checkpoint(run_id: str, wake_at: datetime) -> Checkpoint:
    return Checkpoint(
        run_id=run_id,
        tenant_id="t-test",
        schema_version=CURRENT_SCHEMA_VERSION,
        status="paused",
        round=1,
        rounds_history=[],
        last_request_json='{"payload": "x", "pause_on_round": null}',
        pause_reason="toy",
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        created_at="2026-05-16T12:00:00+00:00",
        updated_at="2026-05-16T12:00:00+00:00",
        wake_at=wake_at.isoformat(),
    )


@pytest.mark.asyncio
async def test_polling_scheduler_returns_ready_tokens(tmp_path: Path) -> None:
    store = MemoryCheckpointStore()
    now = datetime.now(timezone.utc)
    await store.write(make_paused_checkpoint("run-ready", now - timedelta(seconds=5)))
    await store.write(make_paused_checkpoint("run-future", now + timedelta(hours=1)))
    scheduler = PollingScheduler(checkpoint_store=store)
    ready = await scheduler.poll_ready(batch_size=10)
    assert {t.run_id for t in ready} == {"run-ready"}


@pytest.mark.asyncio
async def test_polling_scheduler_respects_batch_size(tmp_path: Path) -> None:
    store = MemoryCheckpointStore()
    now = datetime.now(timezone.utc)
    for i in range(5):
        await store.write(make_paused_checkpoint(f"r{i}", now - timedelta(seconds=1)))
    scheduler = PollingScheduler(checkpoint_store=store)
    ready = await scheduler.poll_ready(batch_size=2)
    assert len(ready) == 2


@pytest.mark.asyncio
async def test_daemon_invokes_factory_per_paused_run(tmp_path: Path) -> None:
    config = make_test_config(tmp_path)
    store = MemoryCheckpointStore()
    now = datetime.now(timezone.utc)
    cp = make_paused_checkpoint("daemonr1", now - timedelta(seconds=1))
    cp.last_request_json = '{"payload": "x", "pause_on_round": null}'
    await store.write(cp)

    invoked: list[str] = []

    def factory(workflow_class: str, tenant_id: str) -> DurableWorkflow:
        invoked.append(workflow_class)
        inner = ToyPausingWorkflow(config=config)
        return DurableWorkflow(inner=inner, config=config, checkpoint_store=store)

    token = ResumeToken(
        run_id="daemonr1",
        workflow_class="tests.unit.durable.fakes.ToyPausingWorkflow",
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        schema_version=CURRENT_SCHEMA_VERSION,
        created_at=cp.created_at,
        wake_at=cp.wake_at,
    )

    daemon = SchedulerDaemon(
        scheduler=PollingScheduler(checkpoint_store=store),
        workflow_factory=factory,
        token_resolver=lambda t: token,
        poll_interval_seconds=0.05,
    )

    task = asyncio.create_task(daemon.run_forever())
    await asyncio.sleep(0.3)
    daemon.stop()
    await task
    assert "tests.unit.durable.fakes.ToyPausingWorkflow" in invoked
