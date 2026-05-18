"""Unit tests for OtelMetricsBackend using OTel in-memory test exporters.

No live network. Constructs MeterProvider / TracerProvider manually so the
backend's __init__ (which builds OTLP exporters) can be bypassed for
test-only assertions on the instrument behavior.
"""
from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry")

from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)


def _make_backend_with_inmemory(monkeypatch):
    """Construct an OtelMetricsBackend whose providers use in-memory readers."""
    from examples.production.durable_postgres_otel import otel_backend as ob

    reader = InMemoryMetricReader()
    span_exporter = InMemorySpanExporter()

    # Patch OTLP exporters to no-op stand-ins so __init__ does not try to
    # contact a real collector during tests.
    class _NoopMetricExporter:
        def __init__(self, *a, **kw): ...
        def export(self, *a, **kw): return True
        def shutdown(self, *a, **kw): ...
        def force_flush(self, *a, **kw): return True

    class _NoopSpanExporter:
        def __init__(self, *a, **kw): ...
        def export(self, *a, **kw): return True
        def shutdown(self, *a, **kw): ...
        def force_flush(self, *a, **kw): return True

    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.grpc.metric_exporter.OTLPMetricExporter",
        _NoopMetricExporter,
    )
    monkeypatch.setattr(
        "opentelemetry.exporter.otlp.proto.grpc.trace_exporter.OTLPSpanExporter",
        _NoopSpanExporter,
    )

    backend = ob.OtelMetricsBackend(service_name="test-svc")

    # Replace MeterProvider with one using the in-memory reader so tests
    # can read recorded metrics deterministically.
    backend._meter_provider = MeterProvider(metric_readers=[reader])  # noqa: SLF001
    backend._meter = backend._meter_provider.get_meter("test")  # noqa: SLF001
    backend._counters.clear()  # noqa: SLF001
    backend._histograms.clear()  # noqa: SLF001
    backend._up_down_counters.clear()  # noqa: SLF001

    # Replace tracer with an in-memory one
    tp = TracerProvider()
    tp.add_span_processor(SimpleSpanProcessor(span_exporter))
    backend._tracer_provider = tp  # noqa: SLF001
    backend._tracer = tp.get_tracer("test")  # noqa: SLF001

    return backend, reader, span_exporter


def test_counter_increments_meter(monkeypatch):
    backend, reader, _ = _make_backend_with_inmemory(monkeypatch)
    backend.counter("durable.workflow.start", value=3, tags={"workflow.class": "X"})
    data = reader.get_metrics_data()
    # Walk: ResourceMetrics -> ScopeMetrics -> Metrics
    names = []
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                names.append(m.name)
    assert "durable.workflow.start" in names


def test_histogram_records_value(monkeypatch):
    backend, reader, _ = _make_backend_with_inmemory(monkeypatch)
    backend.histogram("durable.round.latency_seconds", 1.5)
    backend.timing("durable.round.latency_seconds", 2.5)
    data = reader.get_metrics_data()
    found = False
    for rm in data.resource_metrics:
        for sm in rm.scope_metrics:
            for m in sm.metrics:
                if m.name == "durable.round.latency_seconds":
                    found = True
    assert found


def test_exporter_failure_does_not_propagate(monkeypatch):
    backend, _, _ = _make_backend_with_inmemory(monkeypatch)

    # Sabotage the counter instrument so .add raises
    class _Broken:
        def add(self, *a, **kw):
            raise RuntimeError("exporter down")

    backend._counters["bad"] = _Broken()  # noqa: SLF001
    # Must NOT raise
    backend.counter("bad", value=1)
    # gauge / histogram same posture
    backend._up_down_counters["badg"] = _Broken()  # noqa: SLF001
    backend.gauge("badg", 1.0)

    class _BrokenHist:
        def record(self, *a, **kw):
            raise RuntimeError("exporter down")

    backend._histograms["badh"] = _BrokenHist()  # noqa: SLF001
    backend.histogram("badh", 1.0)


@pytest.mark.asyncio
async def test_span_records_attributes_and_exception(monkeypatch):
    backend, _, span_exporter = _make_backend_with_inmemory(monkeypatch)

    async with backend.span("durable.workflow.round", tags={"phase": "test"}) as sp:
        sp.set_attribute("round.index", 1)

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    assert spans[0].name == "durable.workflow.round"
    assert spans[0].attributes.get("phase") == "test"
    assert spans[0].attributes.get("round.index") == 1

    span_exporter.clear()

    with pytest.raises(ValueError):
        async with backend.span("durable.workflow.round") as sp:
            raise ValueError("test")

    spans = span_exporter.get_finished_spans()
    assert len(spans) == 1
    # Exception was recorded as event
    assert any(e.name == "exception" for e in spans[0].events)
