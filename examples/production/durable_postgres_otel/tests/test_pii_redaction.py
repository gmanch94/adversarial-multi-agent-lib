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


# ---------------------------------------------------------------------------
# A16-H-02: value-level redaction + span name + resource attribute hardening
# ---------------------------------------------------------------------------

pytest.importorskip("opentelemetry.sdk")

from examples.production.durable_postgres_otel.pii_redaction_span_processor import (  # noqa: E402
    _MAX_VALUE_CHARS,
    _filter_resource,
    _redact_value,
    _sanitize_span_name,
)


def test_allowlisted_key_with_long_value_truncated():
    """A16-H-02: allowlisted KEY with PHI-sized VALUE is truncated."""
    tracer, exporter = _build_tracer_with_redaction()
    long_phi = "patient summary " * 50  # ~800 chars >> _MAX_VALUE_CHARS
    with tracer.start_as_current_span("op") as sp:
        sp.set_attribute("pause_reason", long_phi)
    attrs = dict(exporter.get_finished_spans()[0].attributes or {})
    out = attrs.get("pause_reason")
    assert isinstance(out, str)
    assert len(out) <= _MAX_VALUE_CHARS + len("...[truncated]")
    assert out.endswith("...[truncated]")
    assert "patient summary " * 50 not in out


def test_allowlisted_key_with_ssn_shape_value_redacted():
    """A16-H-02: SSN-shape value in an allowlisted KEY gets shape-redacted."""
    # Use the helper directly — set_attribute may coerce; helper is the
    # ground truth for the redaction policy.
    assert _redact_value("patient ssn is 123-45-6789 today") == "[redacted-shape:ssn]"
    assert _redact_value("card 4111111111111111 ends") == "[redacted-shape:cc]"
    assert _redact_value("phone 5551234567 maybe") == "[redacted-shape:long_digits]"
    # Scalars unchanged.
    assert _redact_value(42) == 42
    assert _redact_value(3.14) == 3.14
    assert _redact_value(True) is True
    # Short benign string passes through.
    assert _redact_value("execute") == "execute"


def test_span_name_with_phi_sanitized():
    """A16-H-02: span name carrying PHI (e.g. patient id) is normalized."""
    # Direct helper test — predictable.
    out = _sanitize_span_name("workflow.PAT-001 John Doe @hospital")
    # Spaces and @ replaced with _; dots, hyphens preserved.
    assert " " not in out
    assert "@" not in out
    assert out.startswith("workflow.PAT-001")
    # Truncation at 80 chars.
    long_name = "a" * 200
    assert len(_sanitize_span_name(long_name)) == 80
    # Empty / non-string fallback.
    assert _sanitize_span_name("") == "redacted"
    assert _sanitize_span_name(None) == "redacted"
    # End-to-end: emit a span with PHI in name, verify exporter sees sanitized form.
    tracer, exporter = _build_tracer_with_redaction()
    with tracer.start_as_current_span("workflow.PAT-001 patient name"):
        pass
    name = exporter.get_finished_spans()[0].name
    assert " " not in name
    assert name.startswith("workflow.PAT-001")


def test_resource_attribute_phi_stripped():
    """A16-H-02: caller-supplied resource attrs (hostname carrying tenant)
    are stripped on export; only OTel-standard keys survive."""
    from opentelemetry.sdk.resources import Resource

    raw = Resource.create(
        {
            "service.name": "durable-daemon",
            "service.version": "1.0",
            "host.name": "prod-tenant-acme-corp-001",  # PHI-ish
            "customer.tenant_id": "acme-001",  # PHI-ish
            "telemetry.sdk.name": "opentelemetry",
        }
    )
    filtered = _filter_resource(raw)
    attrs = dict(filtered.attributes or {})
    assert attrs.get("service.name") == "durable-daemon"
    assert attrs.get("service.version") == "1.0"
    assert attrs.get("telemetry.sdk.name") == "opentelemetry"
    assert "host.name" not in attrs
    assert "customer.tenant_id" not in attrs
