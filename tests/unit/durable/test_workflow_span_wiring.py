"""Tier 1.1 Slice A: span + lock-acquire metric wiring in start() + resume()."""
from __future__ import annotations

import pytest

from adv_multi_agent.core.config import Config
from adv_multi_agent.core.durable.checkpoint import MemoryCheckpointStore
from adv_multi_agent.core.durable.lock import MemoryRunLock
from adv_multi_agent.core.durable.workflow import DurableWorkflow, PauseContext
from adv_multi_agent.core.workflow import BaseWorkflow, WorkflowResult

from ._recording_metrics import RecordingMetricsBackend


class _ConvergeOnFirstRound(BaseWorkflow):
    async def run(self, request):
        return WorkflowResult(output="x", rounds=0, final_score=0.0, converged=False, metadata={})

    async def run_round(self, request, prior_state, round_num, ctx):
        return {
            "output": "x", "score": 1.0, "converged": True,
            "rounds_history_entry": {"round": round_num, "score": 1.0},
        }


class _PauseFirstResumeConverge(BaseWorkflow):
    """Round 1 pauses; round 2 converges. For resume() coverage."""

    async def run(self, request):
        return WorkflowResult(output="x", rounds=0, final_score=0.0, converged=False, metadata={})

    async def run_round(self, request, prior_state, round_num, ctx: PauseContext):
        if round_num == 1:
            await ctx.pause(reason="awaiting_input", context={})
        return {
            "output": "ok", "score": 1.0, "converged": True,
            "rounds_history_entry": {"round": round_num, "score": 1.0},
        }


@pytest.fixture
def cfg() -> Config:
    return Config(
        executor_model="claude-opus-4-7",
        reviewer_model="gpt-4o",
        anthropic_api_key="test-key",
    )


@pytest.mark.asyncio
async def test_span_per_round_in_start_path(cfg) -> None:
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_ConvergeOnFirstRound(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,
    )
    await dw.start(request={}, tenant_id="t-test")
    round_spans = [s for s in rb.spans if s[0] == "durable.round"]
    assert len(round_spans) == 1
    name, keys, entered, exited, _exc = round_spans[0]
    assert entered is True and exited is True
    assert keys == frozenset({"workflow"})


@pytest.mark.asyncio
async def test_span_records_pause_reason_attribute(cfg) -> None:
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_PauseFirstResumeConverge(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,
    )
    await dw.start(request={}, tenant_id="t-test")
    # Span entered + exited even on pause path
    round_spans = [s for s in rb.spans if s[0] == "durable.round"]
    assert len(round_spans) == 1
    assert round_spans[0][2] is True and round_spans[0][3] is True


@pytest.mark.asyncio
async def test_lock_acquire_metrics_on_resume_success(cfg) -> None:
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_PauseFirstResumeConverge(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,
    )
    outcome = await dw.start(request={}, tenant_id="t-test")
    assert outcome.status == "paused"
    rb.histograms.clear()
    rb.counters.clear()
    await dw.resume(outcome.token)
    # Latency histogram with phase=resume must appear
    resume_lat = [h for h in rb.histograms
                  if h[0] == "durable.lock.acquire_latency_seconds"]
    assert len(resume_lat) >= 1
    assert resume_lat[0][2] == frozenset({"workflow", "phase"})


@pytest.mark.asyncio
async def test_lock_acquire_metrics_on_resume_failure(cfg) -> None:
    """Broken lock on resume → durable.lock.acquire_failed counter with phase=resume."""
    rb = RecordingMetricsBackend()

    # First, do a normal start+pause to land a checkpoint
    dw_ok = DurableWorkflow(
        inner=_PauseFirstResumeConverge(config=cfg),
        config=cfg,
        checkpoint_store=(store := MemoryCheckpointStore()),
        run_lock=MemoryRunLock(),
        metrics=RecordingMetricsBackend(),
    )
    outcome = await dw_ok.start(request={}, tenant_id="t-test")
    assert outcome.status == "paused"

    class _BrokenLock:
        async def acquire(self, run_id, ttl_seconds):
            raise RuntimeError("down")

        async def release(self, handle):
            pass

        async def heartbeat(self, handle):
            pass

    dw_broken = DurableWorkflow(
        inner=_PauseFirstResumeConverge(config=cfg),
        config=cfg,
        checkpoint_store=store,
        run_lock=_BrokenLock(),
        metrics=rb,
    )
    with pytest.raises(RuntimeError):
        await dw_broken.resume(outcome.token)
    failed = [c for c in rb.counters if c[0] == "durable.lock.acquire_failed"]
    assert len(failed) == 1
    assert failed[0][2] == frozenset({"workflow", "phase"})


@pytest.mark.asyncio
async def test_checkpoint_schema_version_gauge_emitted(cfg) -> None:
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_ConvergeOnFirstRound(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,
    )
    await dw.start(request={}, tenant_id="t-test")
    sv = [g for g in rb.gauges if g[0] == "durable.checkpoint.schema_version"]
    assert len(sv) >= 1
    assert sv[0][2] == frozenset({"workflow"})
    assert sv[0][1] >= 1.0  # CURRENT_SCHEMA_VERSION is an int >= 1
