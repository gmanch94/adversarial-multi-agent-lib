"""OTel-backed MetricsBackend implementation.

Implements the `MetricsBackend` Protocol from
`adv_multi_agent.core.durable.metrics` using OpenTelemetry Python SDK.

Design choices:
- Counter / Histogram primitives map 1:1 to OTel `Counter` / `Histogram`.
- Gauge uses `UpDownCounter` with diff-tracking against a per-tagset cache
  of the last value. Rationale: OTel has no synchronous "set" gauge; the
  alternatives are (a) `ObservableGauge` (requires callbacks, awkward for
  the imperative `gauge(name, value)` shape the library exposes) or
  (b) diff-tracked `UpDownCounter`. (b) is simpler and the operator's
  Prometheus/Grafana sees the same monotonic-ish series either way.
- All exporter exceptions are swallowed per spec §7. Telemetry must never
  break the workflow. We log at WARNING level so operators see degradation
  without blowing up the run.
- Instruments are cached lazily in dicts keyed by name.

PII boundary: this backend does NOT redact attributes. Redaction lives in
`PIIRedactionSpanProcessor` (spans) and in caller discipline (metric tags).
The allowlist enforcement is exporter-side, not library-side.
"""
from __future__ import annotations

import logging
import threading
from contextlib import AbstractAsyncContextManager
from typing import Any, Mapping

_LOG = logging.getLogger(__name__)


def _tags_to_attrs(tags: Mapping[str, str] | None) -> dict[str, str]:
    if not tags:
        return {}
    return dict(tags)


def _tagset_key(tags: Mapping[str, str] | None) -> tuple[tuple[str, str], ...]:
    if not tags:
        return ()
    return tuple(sorted(tags.items()))


class OtelMetricsBackend:
    """OTel-backed MetricsBackend.

    Wires OTel Meter + Tracer providers with OTLP gRPC exporters. Caller
    is responsible for calling `install_pii_redaction()` before producing
    any spans if redaction is required (it is, for the reference deploy).
    """

    def __init__(
        self,
        *,
        service_name: str,
        otlp_endpoint: str = "otel-collector:4317",
        service_version: str = "0.1.0",
    ) -> None:
        # Imports are lazy so importing this module without the OTel SDK
        # installed still raises a clean ImportError naming the package.
        try:
            from opentelemetry import metrics, trace
            from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
                OTLPMetricExporter,
            )
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )
            from opentelemetry.sdk.metrics import MeterProvider
            from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
            from opentelemetry.sdk.resources import Resource
            from opentelemetry.sdk.trace import TracerProvider
            from opentelemetry.sdk.trace.export import BatchSpanProcessor
        except ImportError as exc:  # pragma: no cover
            raise ImportError(
                "OtelMetricsBackend requires opentelemetry-{api,sdk,exporter-otlp-proto-grpc}. "
                "Install via `pip install -r requirements.txt` in this directory."
            ) from exc

        resource = Resource.create(
            {"service.name": service_name, "service.version": service_version}
        )
        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=otlp_endpoint, insecure=True)
        )
        self._meter_provider = MeterProvider(resource=resource, metric_readers=[reader])
        self._meter = self._meter_provider.get_meter(service_name)

        self._tracer_provider = TracerProvider(resource=resource)
        self._span_exporter = OTLPSpanExporter(endpoint=otlp_endpoint, insecure=True)
        # Default downstream is BatchSpanProcessor; install_pii_redaction()
        # wraps it. Operators that skip redaction get unfiltered spans.
        self._downstream_processor: Any = BatchSpanProcessor(self._span_exporter)
        self._tracer_provider.add_span_processor(self._downstream_processor)
        self._tracer = self._tracer_provider.get_tracer(service_name)

        self._counters: dict[str, Any] = {}
        self._histograms: dict[str, Any] = {}
        self._up_down_counters: dict[str, Any] = {}
        # gauge diff-tracking: (name, tagset) -> last value
        self._last_gauge: dict[tuple[str, tuple[tuple[str, str], ...]], float] = {}
        self._gauge_lock = threading.Lock()

        # Expose the global setters for callers that want OTel API-level access
        metrics.set_meter_provider(self._meter_provider)
        trace.set_tracer_provider(self._tracer_provider)

    def install_pii_redaction(self) -> None:
        """Wrap the existing span processor in PIIRedactionSpanProcessor.

        Call before producing any spans. Idempotent: a second call is a no-op.
        """
        from .pii_redaction_span_processor import PIIRedactionSpanProcessor

        if isinstance(self._downstream_processor, PIIRedactionSpanProcessor):
            return
        wrapped = PIIRedactionSpanProcessor(self._downstream_processor)
        # OTel TracerProvider holds processors in a private MultiSpanProcessor;
        # there is no public "replace" API. We swap by clearing and re-adding.
        # `_active_span_processor` is the documented private attr across SDK
        # 1.20+; wrapped in try/except so SDK churn does not break the daemon.
        try:
            multi = self._tracer_provider._active_span_processor  # type: ignore[attr-defined]
            multi._span_processors = (wrapped,)  # type: ignore[attr-defined]
            self._downstream_processor = wrapped
        except AttributeError:
            _LOG.warning(
                "otel.pii_redaction_install_failed",
                extra={"error": "tracer_provider internals changed"},
            )

    # ---- MetricsBackend Protocol ----

    def counter(
        self, name: str, value: int = 1, *, tags: Mapping[str, str] | None = None
    ) -> None:
        try:
            inst = self._counters.get(name)
            if inst is None:
                inst = self._meter.create_counter(name)
                self._counters[name] = inst
            inst.add(value, attributes=_tags_to_attrs(tags))
        except Exception as exc:
            _LOG.warning("otel.counter_failed name=%s error=%s", name, exc)

    def gauge(
        self, name: str, value: float, *, tags: Mapping[str, str] | None = None
    ) -> None:
        try:
            inst = self._up_down_counters.get(name)
            if inst is None:
                inst = self._meter.create_up_down_counter(name)
                self._up_down_counters[name] = inst
            key = (name, _tagset_key(tags))
            with self._gauge_lock:
                last = self._last_gauge.get(key, 0.0)
                delta = value - last
                self._last_gauge[key] = value
            inst.add(delta, attributes=_tags_to_attrs(tags))
        except Exception as exc:
            _LOG.warning("otel.gauge_failed name=%s error=%s", name, exc)

    def histogram(
        self, name: str, value: float, *, tags: Mapping[str, str] | None = None
    ) -> None:
        try:
            inst = self._histograms.get(name)
            if inst is None:
                inst = self._meter.create_histogram(name)
                self._histograms[name] = inst
            inst.record(value, attributes=_tags_to_attrs(tags))
        except Exception as exc:
            _LOG.warning("otel.histogram_failed name=%s error=%s", name, exc)

    def timing(
        self,
        name: str,
        seconds: float,
        *,
        tags: Mapping[str, str] | None = None,
    ) -> None:
        self.histogram(name, seconds, tags=tags)

    def span(
        self,
        name: str,
        *,
        tags: Mapping[str, str] | None = None,
    ) -> AbstractAsyncContextManager["_OtelSpan"]:
        return _OtelSpan(self._tracer, name, _tags_to_attrs(tags))


class _OtelSpan:
    """Async context manager backing `OtelMetricsBackend.span()`.

    All OTel calls are wrapped in try/except — telemetry failure never
    breaks the workflow per spec §7.
    """

    def __init__(self, tracer: Any, name: str, attrs: dict[str, str]) -> None:
        self._tracer = tracer
        self._name = name
        self._attrs = attrs
        self._span: Any = None
        self._cm: Any = None

    async def __aenter__(self) -> "_OtelSpan":
        try:
            self._cm = self._tracer.start_as_current_span(
                self._name, attributes=self._attrs
            )
            self._span = self._cm.__enter__()
        except Exception as exc:
            _LOG.warning("otel.span_enter_failed name=%s error=%s", self._name, exc)
            self._cm = None
            self._span = None
        return self

    async def __aexit__(
        self, exc_type: object, exc: BaseException | None, tb: object
    ) -> bool:
        if self._span is not None and exc is not None:
            try:
                self._span.record_exception(exc)
            except Exception:
                pass
        if self._cm is not None:
            try:
                self._cm.__exit__(exc_type, exc, tb)
            except Exception as inner:
                _LOG.warning(
                    "otel.span_exit_failed name=%s error=%s", self._name, inner
                )
        return False

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        if self._span is None:
            return
        try:
            self._span.set_attribute(key, value)
        except Exception:
            pass

    def record_exception(self, exc: BaseException) -> None:
        if self._span is None:
            return
        try:
            self._span.record_exception(exc)
        except Exception:
            pass


__all__ = ["OtelMetricsBackend", "_OtelSpan"]
