"""Unit tests for PII-redaction SpanProcessor."""
from __future__ import annotations

import pytest

pytest.importorskip("opentelemetry")

from opentelemetry.sdk.trace import Event, TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from examples.production.durable_postgres_otel.pii_redaction_span_processor import (
    PIIRedactionSpanProcessor,
    _sanitize_exception_event,
)


def _build_tracer_with_redaction():
    exporter = InMemorySpanExporter()
    downstream = SimpleSpanProcessor(exporter)
    redactor = PIIRedactionSpanProcessor(downstream)
    tp = TracerProvider()
    tp.add_span_processor(redactor)
    return tp.get_tracer("test"), exporter


def test_phi_attribute_stripped():
    tracer, exporter = _build_tracer_with_redaction()
    with tracer.start_as_current_span("op") as sp:
        sp.set_attribute("patient.mrn", "12345-PHI")
        sp.set_attribute("workflow.class", "SomeWorkflow")
    spans = exporter.get_finished_spans()
    assert len(spans) == 1
    attrs = dict(spans[0].attributes or {})
    assert "patient.mrn" not in attrs
    assert attrs.get("workflow.class") == "SomeWorkflow"


def test_allowlisted_attribute_preserved():
    tracer, exporter = _build_tracer_with_redaction()
    with tracer.start_as_current_span("op") as sp:
        sp.set_attribute("phase", "execute")
        sp.set_attribute("round.index", 2)
        sp.set_attribute("status", "ok")
    attrs = dict(exporter.get_finished_spans()[0].attributes or {})
    assert attrs.get("phase") == "execute"
    assert attrs.get("round.index") == 2
    assert attrs.get("status") == "ok"


def test_exception_event_keeps_type_drops_message_and_stack():
    ev = Event(
        name="exception",
        attributes={
            "exception.type": "RuntimeError",
            "exception.message": "PHI leaked here",
            "exception.stacktrace": "Traceback PHI ...",
        },
    )
    redacted = _sanitize_exception_event(ev)
    attrs = dict(redacted.attributes or {})
    assert attrs.get("exception.type") == "RuntimeError"
    assert "exception.message" not in attrs
    assert "exception.stacktrace" not in attrs


def test_non_exception_event_dropped_when_unsafe_attrs():
    # Non-exception event with a non-allowlisted attribute should be dropped.
    ev = Event(name="custom.event", attributes={"patient.mrn": "PHI"})
    assert _sanitize_exception_event(ev) is None

    # Non-exception event with ONLY allowlisted attributes passes through.
    ev2 = Event(name="custom.event", attributes={"phase": "execute"})
    assert _sanitize_exception_event(ev2) is ev2
