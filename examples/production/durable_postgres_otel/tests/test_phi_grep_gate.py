"""PHI grep gate — integration test.

Runs a synthetic 'workflow' that intentionally tries to leak PHI through:
- span attributes with PHI-shaped keys/values
- exception event messages + stacktraces
- non-allowlisted event attributes

The PIIRedactionSpanProcessor sits in front of an InMemorySpanExporter.
After flush, every exported span is dumped to JSON and grepped for known
PHI markers. Failure (any marker present) means the redactor has a hole.

This is the defense layer that catches D-OTEL-2 regressions at PR time.
"""
from __future__ import annotations

import json

import pytest

pytest.importorskip("opentelemetry.sdk")

from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from examples.production.durable_postgres_otel.pii_redaction_span_processor import (
    PIIRedactionSpanProcessor,
)


# Markers that MUST NOT appear in exported span JSON.
# - gAAAAA: Fernet token prefix (base64-encoded version + timestamp)
# - :5432/: postgres DSN shape (host:port/db); catches accidental DSN logging
# - password=: any KV form for a password
# - SSN/MRN/PATIENT *_FAKE_PATTERN: synthetic PHI markers we plant in the workflow
_FORBIDDEN_MARKERS = (
    "gAAAAA",
    ":5432/",
    "password=",
    "SSN_FAKE_PATTERN_999_88_7777",
    "MRN_FAKE_PATTERN_ABC123",
    "PATIENT_FAKE_PATTERN_JohnDoe",
)


def _build_tracer_with_redaction():
    exporter = InMemorySpanExporter()
    downstream = SimpleSpanProcessor(exporter)
    redactor = PIIRedactionSpanProcessor(downstream)
    tp = TracerProvider()
    tp.add_span_processor(redactor)
    return tp.get_tracer("phi-grep-gate"), exporter


def _synthetic_phi_leaking_workflow(tracer) -> None:
    """Touches every leak vector the redactor MUST close."""
    # Vector 1: span attribute with PHI key + value
    with tracer.start_as_current_span("round") as sp:
        sp.set_attribute("workflow.class", "SyntheticWorkflow")  # allowlisted
        sp.set_attribute("patient.ssn", "SSN_FAKE_PATTERN_999_88_7777")
        sp.set_attribute("patient.mrn", "MRN_FAKE_PATTERN_ABC123")
        sp.set_attribute("patient.name", "PATIENT_FAKE_PATTERN_JohnDoe")
        sp.set_attribute(
            "db.dsn",
            "postgresql://daemon:hunter2@db.internal:5432/durable",
        )
        sp.set_attribute("fernet.token", "gAAAAABabcdefghijklmnop_synthetic")

    # Vector 2: exception with PHI in message and traceback
    with tracer.start_as_current_span("round-with-exception") as sp:
        try:
            raise ValueError(
                "patient SSN_FAKE_PATTERN_999_88_7777 connection "
                "postgresql://x:password=hunter2@db:5432/d failed"
            )
        except ValueError as e:
            sp.record_exception(e)

    # Vector 3: arbitrary event with non-allowlisted attribute
    with tracer.start_as_current_span("round-with-event") as sp:
        sp.add_event(
            "custom.event",
            attributes={"leak.field": "MRN_FAKE_PATTERN_ABC123"},
        )


def _spans_to_json(spans) -> str:
    """Serialize every exported span (attrs + events + event-attrs) to one JSON blob.

    Uses the OTel-SDK to_json() helper when available; falls back to a hand-rolled
    dump that exhausts every place a string could hide.
    """
    parts: list[str] = []
    for sp in spans:
        try:
            parts.append(sp.to_json())  # SDK serializer
        except Exception:
            # Manual exhaustive dump as belt-and-suspenders
            parts.append(
                json.dumps(
                    {
                        "name": sp.name,
                        "attributes": dict(sp.attributes or {}),
                        "events": [
                            {
                                "name": ev.name,
                                "attributes": dict(ev.attributes or {}),
                            }
                            for ev in (sp.events or [])
                        ],
                    },
                    default=str,
                )
            )
    return "\n".join(parts)


def test_no_phi_markers_in_exported_spans():
    tracer, exporter = _build_tracer_with_redaction()
    _synthetic_phi_leaking_workflow(tracer)

    spans = exporter.get_finished_spans()
    assert len(spans) == 3, "all three synthetic spans should export"

    blob = _spans_to_json(spans)

    hits = [m for m in _FORBIDDEN_MARKERS if m in blob]
    assert hits == [], (
        f"PHI grep gate FAILED. Markers leaked through redaction: {hits}\n"
        f"Exported span JSON (truncated 2KB):\n{blob[:2048]}"
    )


def test_allowlisted_attribute_still_exports():
    """Sanity check the redactor isn't a strip-everything bug."""
    tracer, exporter = _build_tracer_with_redaction()
    _synthetic_phi_leaking_workflow(tracer)

    spans = exporter.get_finished_spans()
    first_attrs = dict(spans[0].attributes or {})
    assert first_attrs.get("workflow.class") == "SyntheticWorkflow"
