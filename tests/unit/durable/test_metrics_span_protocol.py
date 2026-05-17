"""Tier 1.1 Slice A: MetricsBackend.span() Protocol + _NoopSpan behavior."""
from __future__ import annotations

import asyncio
import time

import pytest

from adv_multi_agent.core.durable.metrics import NoopMetricsBackend, _NoopSpan


@pytest.mark.asyncio
async def test_noop_span_zero_overhead() -> None:
    """1000 enter/exit cycles complete in well under 100ms."""
    m = NoopMetricsBackend()
    t0 = time.perf_counter()
    for _ in range(1000):
        async with m.span("durable.round", tags={"workflow": "X"}):
            pass
    elapsed = time.perf_counter() - t0
    # Generous bound — pytest-asyncio overhead dominates; we want to catch
    # accidental sync I/O / allocation regressions, not measure µs precisely.
    assert elapsed < 0.5, f"1000 noop spans took {elapsed:.3f}s"


@pytest.mark.asyncio
async def test_noop_span_records_exception_silently() -> None:
    """record_exception on Noop span is a no-op (no raise, no side effect)."""
    m = NoopMetricsBackend()
    async with m.span("x") as span:
        span.record_exception(RuntimeError("boom"))  # must not raise


@pytest.mark.asyncio
async def test_noop_span_set_attribute_silently() -> None:
    m = NoopMetricsBackend()
    async with m.span("x") as span:
        span.set_attribute("workflow.class", "Demo")
        span.set_attribute("round.index", 3)
        span.set_attribute("round.converged", True)
        span.set_attribute("latency_seconds", 0.42)


def test_noop_span_class_is_async_ctx_mgr() -> None:
    """Sanity: _NoopSpan exposes __aenter__/__aexit__."""
    s = _NoopSpan()
    assert asyncio.iscoroutinefunction(s.__aenter__)
    assert asyncio.iscoroutinefunction(s.__aexit__)
