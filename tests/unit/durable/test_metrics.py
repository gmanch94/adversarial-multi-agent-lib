"""Tests for the MetricsBackend Protocol + NoopMetricsBackend + DurableWorkflow wiring.

Tier 1.1 scaffold. Three areas:
1. NoopMetricsBackend swallows all calls (no exceptions, no side effects)
2. Protocol structural typing — any class with the 4 methods is accepted
3. DurableWorkflow emits start/lock-fail/pause counter events at the right sites
"""
from __future__ import annotations

from typing import Mapping

import pytest

from adv_multi_agent.core.config import Config
from adv_multi_agent.core.durable.checkpoint import MemoryCheckpointStore
from adv_multi_agent.core.durable.lock import MemoryRunLock
from adv_multi_agent.core.durable.metrics import NoopMetricsBackend
from adv_multi_agent.core.durable.workflow import DurableWorkflow, PauseContext
from adv_multi_agent.core.workflow import BaseWorkflow, WorkflowResult


# ---------------- Recording fixture ----------------


class RecordingMetricsBackend:
    """Test impl that records every call for assertion."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, float, dict[str, str]]] = []

    def counter(
        self, name: str, value: int = 1, *, tags: Mapping[str, str] | None = None
    ) -> None:
        self.calls.append(("counter", name, float(value), dict(tags or {})))

    def gauge(
        self, name: str, value: float, *, tags: Mapping[str, str] | None = None
    ) -> None:
        self.calls.append(("gauge", name, float(value), dict(tags or {})))

    def histogram(
        self, name: str, value: float, *, tags: Mapping[str, str] | None = None
    ) -> None:
        self.calls.append(("histogram", name, float(value), dict(tags or {})))

    def timing(
        self,
        name: str,
        seconds: float,
        *,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        self.calls.append(("timing", name, float(seconds), dict(tags or {})))

    def span(
        self, name: str, *, tags: Mapping[str, str] | None = None
    ):
        from adv_multi_agent.core.durable.metrics import _NoopSpan
        self.calls.append(("span", name, 0.0, dict(tags or {})))
        return _NoopSpan()


# ---------------- NoopMetricsBackend ----------------


def test_noop_counter_returns_none():
    assert NoopMetricsBackend().counter("x") is None


def test_noop_gauge_returns_none():
    assert NoopMetricsBackend().gauge("x", 1.0) is None


def test_noop_histogram_returns_none():
    assert NoopMetricsBackend().histogram("x", 1.0) is None


def test_noop_timing_returns_none():
    assert NoopMetricsBackend().timing("x", 0.1) is None


def test_noop_accepts_tags_kwarg():
    NoopMetricsBackend().counter("x", tags={"k": "v"})
    NoopMetricsBackend().gauge("x", 1.0, tags={"k": "v"})
    NoopMetricsBackend().histogram("x", 1.0, tags={"k": "v"})
    NoopMetricsBackend().timing("x", 0.1, tags={"k": "v"})


# ---------------- Protocol structural typing ----------------


def test_recording_backend_has_metrics_backend_shape():
    """MetricsBackend is structural (not @runtime_checkable). Verify via attrs."""
    rb = RecordingMetricsBackend()
    for method in ("counter", "gauge", "histogram", "timing"):
        assert callable(getattr(rb, method, None)), f"missing {method}"


# ---------------- DurableWorkflow wiring ----------------


class _ConvergingWorkflow(BaseWorkflow):
    """One-shot workflow that returns a converged result immediately."""

    async def run(self, request):
        return WorkflowResult(
            final_output="x", rounds=1, final_score=1.0, converged=True, metadata={}
        )


class _PausingWorkflow(BaseWorkflow):
    """Workflow that pauses on first invocation."""

    async def run(self, request):
        # Required by BaseWorkflow ABC; not called when run_round exists.
        return WorkflowResult(
            final_output="unused", rounds=0, final_score=0.0, converged=False, metadata={}
        )

    async def run_round(self, request, prior_state, round_num, ctx: PauseContext):
        # DurableWorkflow.start iterates round_num from 1..max_review_rounds.
        if round_num == 1:
            await ctx.pause(reason="rolling_data", context={})
        return {"draft": "x", "score": 1.0, "converged": True}


@pytest.fixture
def cfg():
    return Config(
        executor_model="claude-opus-4-7",
        reviewer_model="gpt-4o",
        anthropic_api_key="test-key",
    )


def test_default_metrics_is_noop(cfg):
    dw = DurableWorkflow(inner=_ConvergingWorkflow(config=cfg), config=cfg)
    assert isinstance(dw._metrics, NoopMetricsBackend)


def test_caller_supplied_metrics_honored(cfg):
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(inner=_ConvergingWorkflow(config=cfg), config=cfg, metrics=rb)
    assert dw._metrics is rb


@pytest.mark.asyncio
async def test_start_emits_workflow_start_counter(cfg):
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_ConvergingWorkflow(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,
    )
    await dw.start(request={})
    start_events = [c for c in rb.calls if c[1] == "durable.workflow.start"]
    assert len(start_events) == 1
    assert start_events[0][3] == {"workflow": "_ConvergingWorkflow"}


@pytest.mark.asyncio
async def test_lock_acquire_failure_emits_counter(cfg):
    """Lock that always raises → counter durable.lock.acquire_failed fires."""
    rb = RecordingMetricsBackend()

    class _BrokenLock:
        async def acquire(self, run_id, ttl_seconds):
            raise RuntimeError("lock down")

        async def release(self, handle):
            pass

        async def heartbeat(self, handle):
            pass

    dw = DurableWorkflow(
        inner=_ConvergingWorkflow(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=_BrokenLock(),
        metrics=rb,
    )
    outcome = await dw.start(request={})
    assert outcome.status == "failed"
    fail_events = [c for c in rb.calls if c[1] == "durable.lock.acquire_failed"]
    assert len(fail_events) == 1
    assert fail_events[0][3]["phase"] == "start"


@pytest.mark.asyncio
async def test_pause_emits_pause_counter_with_reason_tag(cfg):
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_PausingWorkflow(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,
    )
    await dw.start(request={})
    pause_events = [c for c in rb.calls if c[1] == "durable.workflow.pause"]
    assert len(pause_events) == 1
    assert pause_events[0][3]["workflow"] == "_PausingWorkflow"
    assert pause_events[0][3]["pause_reason"] == "rolling_data"


def test_noop_zero_call_overhead():
    """Sanity: 10k Noop counter calls complete in well under 1s."""
    import time
    m = NoopMetricsBackend()
    t0 = time.perf_counter()
    for _ in range(10_000):
        m.counter("x", tags={"k": "v"})
    elapsed = time.perf_counter() - t0
    assert elapsed < 1.0, f"Noop counter took {elapsed:.3f}s for 10k calls"


# ---------------- Tier 1.1 extensions: histograms + budget gauges ----------------


class _ConvergingRoundWorkflow(BaseWorkflow):
    """run_round workflow that converges on round 1 (no pause)."""

    async def run(self, request):
        return WorkflowResult(
            final_output="unused", rounds=0, final_score=0.0, converged=False, metadata={}
        )

    async def run_round(self, request, prior_state, round_num, ctx):
        return {
            "output": "x",
            "score": 1.0,
            "converged": True,
            "rounds_history_entry": {"round": round_num, "score": 1.0},
        }


@pytest.mark.asyncio
async def test_round_latency_histogram_emitted_on_success(cfg):
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_ConvergingRoundWorkflow(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,
    )
    await dw.start(request={})
    hist = [c for c in rb.calls if c[1] == "durable.round.latency_seconds"]
    assert len(hist) >= 1
    # Non-negative latency; tagged by workflow class
    assert hist[0][2] >= 0.0
    assert hist[0][3]["workflow"] == "_ConvergingRoundWorkflow"


@pytest.mark.asyncio
async def test_round_latency_not_emitted_on_pause(cfg):
    """Pause path short-circuits before the histogram emit point — no histogram."""
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_PausingWorkflow(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,
    )
    await dw.start(request={})
    hist = [c for c in rb.calls if c[1] == "durable.round.latency_seconds"]
    assert hist == [], f"expected no histogram on pause path, got {hist}"


@pytest.mark.asyncio
async def test_lock_acquire_latency_histogram_emitted_on_success(cfg):
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_ConvergingWorkflow(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,
    )
    await dw.start(request={})
    hist = [c for c in rb.calls if c[1] == "durable.lock.acquire_latency_seconds"]
    assert len(hist) == 1
    assert hist[0][2] >= 0.0
    assert hist[0][3]["phase"] == "start"


@pytest.mark.asyncio
async def test_lock_acquire_latency_not_emitted_on_failure(cfg):
    """Failure path returns early; histogram unreachable."""
    rb = RecordingMetricsBackend()

    class _BrokenLock:
        async def acquire(self, run_id, ttl_seconds):
            raise RuntimeError("down")

        async def release(self, handle):
            pass

        async def heartbeat(self, handle):
            pass

    dw = DurableWorkflow(
        inner=_ConvergingWorkflow(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=_BrokenLock(),
        metrics=rb,
    )
    await dw.start(request={})
    hist = [c for c in rb.calls if c[1] == "durable.lock.acquire_latency_seconds"]
    assert hist == []


@pytest.mark.asyncio
async def test_budget_gauges_emitted_per_round(cfg):
    from adv_multi_agent.core.durable.budget import BudgetTracker

    rb = RecordingMetricsBackend()
    budget = BudgetTracker(max_tokens_in=1_000_000, max_tokens_out=500_000, max_usd=50.0)
    dw = DurableWorkflow(
        inner=_ConvergingRoundWorkflow(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        budget_tracker=budget,
        metrics=rb,
    )
    await dw.start(request={})
    names = {c[1] for c in rb.calls if c[0] == "gauge"}
    assert "durable.budget.tokens_in" in names
    assert "durable.budget.tokens_out" in names
    assert "durable.budget.usd_spent" in names


@pytest.mark.asyncio
async def test_budget_gauges_not_emitted_without_budget_tracker(cfg):
    rb = RecordingMetricsBackend()
    dw = DurableWorkflow(
        inner=_ConvergingRoundWorkflow(config=cfg),
        config=cfg,
        checkpoint_store=MemoryCheckpointStore(),
        run_lock=MemoryRunLock(),
        metrics=rb,  # no budget_tracker
    )
    await dw.start(request={})
    names = {c[1] for c in rb.calls if c[0] == "gauge"}
    assert not any(n.startswith("durable.budget.") for n in names)
