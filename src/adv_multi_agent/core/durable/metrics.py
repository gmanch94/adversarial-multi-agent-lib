"""MetricsBackend Protocol + NoopMetricsBackend default.

Tier 1.1 scaffold (per `docs/production-readiness-gaps.md`).

The library defines a small structured-metrics seam so operators can wire
OpenTelemetry / Prometheus / Datadog / custom telemetry without the library
depending on any of them. The default `NoopMetricsBackend` is a zero-overhead
no-op so the existing code paths pay nothing.

Why now (vs full OTel deployment): the OTel exporter, Grafana dashboards,
and alert rules belong in a sibling reference deployment under
`examples/production/durable_postgres_otel/`. The Protocol + Noop default
land first so the library wiring is stable across future exporter-backend
churn.

Why this shape (counter/gauge/histogram/timing instead of OTel API directly):
- Decouples library from any specific exporter SDK
- Lets operators ship Prometheus push-gateway, Datadog statsd, or OTLP with
  the same library code
- Noop default keeps `pip install adv-multi-agent` dependency-free
- Future addition of an `MetricsBackend.span(name)` async ctx manager will
  cover tracing without redesigning this surface

Operator wiring pattern:
    from adv_multi_agent.core.durable.metrics import MetricsBackend, NoopMetricsBackend
    from examples.production.durable_postgres_otel.otel_backend import OtelMetricsBackend

    metrics: MetricsBackend = OtelMetricsBackend(...)  # caller-supplied
    DurableWorkflow(inner=..., config=..., metrics=metrics)

PII boundary (per Tier 1.7): tag values passed to `counter`/`gauge`/
`histogram`/`timing` MUST NOT contain per-request PII. Use stable
low-cardinality tags only (workflow_class, pause_reason, status, model
fingerprint). Exporter-side redaction is the second line of defense.

Cardinality boundary: tag values must come from a bounded set (workflow
class names, enum-shaped pause reasons, model strings). Unbounded tags
(run_id, user_id, free-form errors) explode metric cardinality and break
the operator's monitoring backend; library will not detect this — it is a
caller-side discipline anchored in the runbook.
"""
from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import Mapping, Protocol


class Span(Protocol):
    """Minimal span surface — OTel-compatible subset.

    Decouples library from any specific tracing SDK. An OTel-backed
    implementation maps these to `opentelemetry.trace.Span.set_attribute` and
    `record_exception`; a Datadog/Honeycomb/custom impl can do the same.

    PII boundary (Tier 1.7): span names, attribute keys, attribute values, and
    tag values MUST NOT contain per-request PII. Use stable low-cardinality
    strings only. Exporter-side `SpanProcessor` redaction is the second line
    of defense; the library does not redact.
    """

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        """Attach a key/value attribute to this span."""
        ...

    def record_exception(self, exc: BaseException) -> None:
        """Record an exception against this span. Does NOT mark span errored
        automatically — that decision belongs to the caller (some exceptions
        are control-flow signals, e.g. `_PauseSignal`)."""
        ...


class MetricsBackend(Protocol):
    """Structured-metrics seam for the durable subpackage.

    The four primitives map cleanly to OTel + Prometheus + Datadog:
    - `counter` → monotonic counter
    - `gauge` → instantaneous value (set, not delta)
    - `histogram` → bucketed distribution (latency, batch size)
    - `timing` → convenience wrapper around `histogram` in seconds

    Implementations should be thread-safe; the library may invoke from
    `asyncio.to_thread` contexts identical to the `Cipher` Protocol.

    Implementations should NOT raise on metric emission. Telemetry failures
    must never break the workflow. Swallow and log internally.
    """

    def counter(
        self, name: str, value: int = 1, *, tags: Mapping[str, str] | None = None
    ) -> None:
        """Increment a monotonic counter by ``value`` (default 1).

        Example: ``metrics.counter("durable.workflow.start", tags={"workflow": cls})``
        """
        ...

    def gauge(
        self, name: str, value: float, *, tags: Mapping[str, str] | None = None
    ) -> None:
        """Set a gauge to ``value`` (overwrite, not delta).

        Example: ``metrics.gauge("durable.budget.usd_spent", 12.34, tags={...})``
        """
        ...

    def histogram(
        self, name: str, value: float, *, tags: Mapping[str, str] | None = None
    ) -> None:
        """Record one observation into a bucketed distribution.

        Example: ``metrics.histogram("durable.round.latency_seconds", 4.21, ...)``
        """
        ...

    def timing(
        self,
        name: str,
        seconds: float,
        *,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        """Convenience: record ``seconds`` as a histogram observation.

        Equivalent to ``histogram(name, seconds, tags=tags)`` but typed for
        latency-shaped values. Exporter may choose to bucket differently.
        """
        ...

    def span(
        self,
        name: str,
        *,
        tags: Mapping[str, str] | None = None,
    ) -> AbstractAsyncContextManager[Span]:
        """Start a span as an async context manager (D-OTEL-1).

        Library wire points are inside ``async def`` methods; ``async with`` is
        idiomatic. The returned `Span` exposes `set_attribute` and
        `record_exception`. PII boundary applies to span names, attribute
        values, and tag values identically — caller must keep them low-
        cardinality + PHI-free.

        Implementations MUST NOT raise from `span()` or from the returned
        context manager's `__aenter__/__aexit__`. Telemetry never breaks the
        workflow.
        """
        ...


class _NoopSpan:
    """Zero-overhead default span. Methods are no-ops; context manager exits
    cleanly without suppressing exceptions."""

    async def __aenter__(self) -> "_NoopSpan":
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        return None

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        return

    def record_exception(self, exc: BaseException) -> None:
        return


class NoopMetricsBackend:
    """Default zero-overhead backend. Swallows every call.

    Implements MetricsBackend Protocol by structural typing. No state, no
    locking, no allocations beyond the parameter bind. Wraps every method
    in a single-line return so CPython's bytecode is minimal.
    """

    def counter(
        self, name: str, value: int = 1, *, tags: Mapping[str, str] | None = None
    ) -> None:
        return

    def gauge(
        self, name: str, value: float, *, tags: Mapping[str, str] | None = None
    ) -> None:
        return

    def histogram(
        self, name: str, value: float, *, tags: Mapping[str, str] | None = None
    ) -> None:
        return

    def timing(
        self,
        name: str,
        seconds: float,
        *,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        return

    def span(
        self,
        name: str,
        *,
        tags: Mapping[str, str] | None = None,
    ) -> AbstractAsyncContextManager["_NoopSpan"]:
        return _NoopSpan()


__all__ = ["MetricsBackend", "NoopMetricsBackend", "Span"]
