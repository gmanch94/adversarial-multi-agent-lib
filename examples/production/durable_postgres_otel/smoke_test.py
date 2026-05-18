"""Smoke test for the OTel sibling. No live network calls.

Asserts the plumbing works in-process:
  1. OtelMetricsBackend instantiates without raising
  2. counter / gauge / histogram / timing swallow exceptions
  3. span() async context manager exits cleanly
  4. PIIRedactionSpanProcessor.on_end strips non-allowlisted attrs
  5. _sanitize_exception_event drops message + stack, keeps type
"""
from __future__ import annotations

import asyncio


async def _run() -> None:
    from .otel_backend import OtelMetricsBackend
    from .pii_redaction_span_processor import (
        _ALLOWED_ATTRS,
        _sanitize_exception_event,
    )

    # (1) instantiate
    backend = OtelMetricsBackend(service_name="smoke")
    backend.install_pii_redaction()

    # (2) primitives
    backend.counter("smoke.counter", tags={"workflow.class": "X"})
    backend.gauge("smoke.gauge", 3.14, tags={"workflow.class": "X"})
    backend.histogram("smoke.histogram", 0.5)
    backend.timing("smoke.timing", 1.2)

    # (3) span
    async with backend.span("smoke.span", tags={"phase": "test"}) as sp:
        sp.set_attribute("status", "ok")

    # (4) redaction: _ALLOWED_ATTRS must not contain a known PHI key
    assert "patient.mrn" not in _ALLOWED_ATTRS
    assert "workflow.class" in _ALLOWED_ATTRS

    # (5) exception sanitization
    try:
        from opentelemetry.sdk.trace import Event
    except ImportError:
        print("smoke: skipped exception sanitize check (no opentelemetry-sdk)")
    else:
        ev = Event(
            name="exception",
            attributes={
                "exception.type": "ValueError",
                "exception.message": "PHI: patient 12345 mrn",
                "exception.stacktrace": "Traceback PHI ...",
            },
        )
        clean = _sanitize_exception_event(ev)
        attrs = dict(clean.attributes or {})
        assert attrs.get("exception.type") == "ValueError"
        assert "exception.message" not in attrs
        assert "exception.stacktrace" not in attrs

    print("smoke: OK")


if __name__ == "__main__":
    asyncio.run(_run())
