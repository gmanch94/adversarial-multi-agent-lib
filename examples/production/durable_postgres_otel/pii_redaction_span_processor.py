"""PII-redaction SpanProcessor for the OTel sibling deployment.

Per spec D-OTEL-2: span attributes are filtered to a strict allowlist on
export, and exception events are sanitized (type kept; message + stacktrace
dropped). This is the second line of defense — the library's PII boundary
documentation asks callers to keep span attributes low-cardinality + PHI-
free, but the redactor enforces it on export.

Design:
- OTel `ReadableSpan` is immutable. We build a duck-typed `_RedactedSpan`
  proxy that re-implements the public read surface (`attributes`, `events`,
  `name`, `context`, `kind`, `parent`, `start_time`, `end_time`, `status`,
  `resource`, `instrumentation_scope`, `links`) reading from filtered
  copies. The downstream BatchSpanProcessor/exporter accesses spans via
  this read surface only, so the proxy is sufficient.
- We pass the proxy to `downstream.on_end(proxy)`. The original span is
  discarded after this method returns.

Failure mode: if the OTel SDK changes the read surface, the proxy may
expose stale data or AttributeError. We catch broadly and fall through
to a fully-stripped span (all attrs removed, no events) — secure default.
"""
from __future__ import annotations

import logging
import re
from typing import Any

_LOG = logging.getLogger(__name__)

# A16-H-02 closure: cap allowlisted attribute VALUES too, not just KEYS.
# Allowlisted keys (e.g. pause_reason, error_class) can carry unbounded PHI
# if a caller passes raw request content. Truncation + shape-based redaction
# are the second line of defense behind low-cardinality caller discipline.
_MAX_VALUE_CHARS = 128

# Regex denylist for obvious PHI shapes — SSN, long CC runs, raw long digit
# runs. Patterns deliberately conservative to avoid false-positive on
# legitimate identifiers (round.index, attempt.index are ints, not strings).
_VALUE_DENYLIST_PATTERNS: list[tuple[str, "re.Pattern[str]"]] = [
    ("ssn", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("cc", re.compile(r"\b\d{16}\b")),
    ("long_digits", re.compile(r"\b\d{10,}\b")),
]

# Span name normalization: anything not in this charset is replaced with `_`
# and the result is truncated to 80 chars. Drops PHI smuggled via span names
# like f"workflow.{patient_id}".
_SPAN_NAME_SAFE_RE = re.compile(r"[^a-zA-Z0-9._\-:/]")
_MAX_SPAN_NAME_CHARS = 80

# Resource attribute allowlist — OTel-standard keys only. Caller-supplied
# resource attributes (e.g. customer_tenant_id, hostname carrying customer
# initials) get stripped on export.
_ALLOWED_RESOURCE_KEYS: frozenset[str] = frozenset(
    {
        "service.name",
        "service.version",
        "service.namespace",
        "service.instance.id",
        "telemetry.sdk.name",
        "telemetry.sdk.version",
        "telemetry.sdk.language",
        "otel.scope.name",
        "otel.scope.version",
    }
)


# D-OTEL-2: strict allowlist. Adding a key here is a security review point.
_ALLOWED_ATTRS: frozenset[str] = frozenset(
    {
        # Library-emitted (Slice A wired)
        "workflow.class",
        "workflow.version_hash",
        "workflow.schema_version",
        "pause_reason",
        "phase",
        "cipher_backend",
        "lock_backend",
        "status",
        "error_class",
        "model_fingerprint",
        "round.index",
        "round.converged",
        "round.paused",
        "attempt.index",
        "latency_seconds",
        "duration_ms",
        # OTel standard / resource attrs
        "service.name",
        "service.version",
        "telemetry.sdk.name",
        "telemetry.sdk.version",
        "telemetry.sdk.language",
        "otel.scope.name",
        "otel.scope.version",
        "span.kind",
    }
)


def _redact_value(v: Any) -> Any:
    """A16-H-02: scrub allowlisted attribute VALUES.

    - Strings exceeding `_MAX_VALUE_CHARS` are truncated with marker.
    - Strings matching denylist patterns (SSN, CC, long-digit runs) are
      replaced with `[redacted-shape:<name>]`.
    - Lists/dicts (non-scalar) are coerced to `"[redacted-nonscalar]"`
      since their nested values aren't filtered.
    - Other scalars (int, float, bool) pass through unchanged.
    """
    if isinstance(v, (int, float, bool)) or v is None:
        return v
    if isinstance(v, str):
        for name, pat in _VALUE_DENYLIST_PATTERNS:
            if pat.search(v):
                return f"[redacted-shape:{name}]"
        if len(v) > _MAX_VALUE_CHARS:
            return v[:_MAX_VALUE_CHARS] + "...[truncated]"
        return v
    # Non-scalar (list, dict, tuple, set, custom): too risky to ship.
    return "[redacted-nonscalar]"


def _filter_attrs(attrs: Any) -> dict[str, Any]:
    """Return new dict with only allowlisted keys + scrubbed values.
    Secure default on error."""
    if attrs is None:
        return {}
    try:
        return {
            k: _redact_value(v)
            for k, v in dict(attrs).items()
            if k in _ALLOWED_ATTRS
        }
    except Exception:
        return {}


def _sanitize_span_name(name: Any) -> str:
    """A16-H-02: drop PHI smuggled via span name (e.g. f'workflow.{patient_id}').
    Replaces unsafe chars with `_` and truncates to `_MAX_SPAN_NAME_CHARS`."""
    if not isinstance(name, str):
        return "redacted"
    cleaned = _SPAN_NAME_SAFE_RE.sub("_", name)
    if len(cleaned) > _MAX_SPAN_NAME_CHARS:
        cleaned = cleaned[:_MAX_SPAN_NAME_CHARS]
    return cleaned or "redacted"


def _filter_resource(resource: Any) -> Any:
    """A16-H-02: filter Resource attributes to OTel-standard keys only.
    Caller-supplied resource attrs (hostname, tenant id) get stripped."""
    if resource is None:
        return resource
    try:
        from opentelemetry.sdk.resources import Resource  # type: ignore[import-not-found]
    except ImportError:
        return resource
    try:
        raw = dict(getattr(resource, "attributes", {}) or {})
        filtered = {k: v for k, v in raw.items() if k in _ALLOWED_RESOURCE_KEYS}
        return Resource.create(filtered)
    except Exception:
        # Secure default: empty resource rather than leaking.
        try:
            return Resource.create({})
        except Exception:
            return resource


def _sanitize_exception_event(event: Any) -> Any:
    """Strip `exception.message` and `exception.stacktrace`; keep `exception.type`.

    Stacktrace and message can contain formatted request_json fragments
    (PHI). The type alone is low-cardinality and useful for alerting.
    """
    try:
        from opentelemetry.sdk.trace import Event
    except ImportError:
        return event

    name = getattr(event, "name", "")
    if name != "exception":
        # Non-exception events: pass through ONLY if all attribute keys are
        # allowlisted. Otherwise drop the entire event (secure default).
        attrs = getattr(event, "attributes", None) or {}
        try:
            for k in dict(attrs).keys():
                if k not in _ALLOWED_ATTRS:
                    return None
        except Exception:
            return None
        return event

    attrs = getattr(event, "attributes", None) or {}
    try:
        exc_type = dict(attrs).get("exception.type", "unknown")
    except Exception:
        exc_type = "unknown"
    return Event(
        name="exception",
        attributes={"exception.type": exc_type},
        timestamp=getattr(event, "timestamp", None),
    )


def _redact_events(events: Any) -> list[Any]:
    if not events:
        return []
    out: list[Any] = []
    try:
        for ev in events:
            redacted = _sanitize_exception_event(ev)
            if redacted is not None:
                out.append(redacted)
    except Exception:
        return []
    return out


class _RedactedSpan:
    """Read-surface proxy for a ReadableSpan with filtered attributes/events."""

    def __init__(self, original: Any) -> None:
        self._original = original
        self._attrs = _filter_attrs(getattr(original, "attributes", None))
        self._events = _redact_events(getattr(original, "events", None))
        # A16-H-02: pre-compute sanitized name + filtered resource so the
        # exporter cannot reach the raw values via property re-evaluation.
        self._name = _sanitize_span_name(getattr(original, "name", ""))
        self._resource = _filter_resource(getattr(original, "resource", None))

    # OTel exporter read surface — delegate everything except attrs/events/name/resource.
    @property
    def attributes(self) -> dict[str, Any]:
        return self._attrs

    @property
    def events(self) -> list[Any]:
        return self._events

    @property
    def name(self) -> str:
        """A16-H-02: sanitized span name — drops PHI smuggled via name template."""
        return self._name

    @property
    def resource(self) -> Any:
        """A16-H-02: filtered resource — only OTel-standard keys survive."""
        return self._resource

    def __getattr__(self, item: str) -> Any:
        # Anything not overridden falls through to the original span.
        return getattr(self._original, item)


class PIIRedactionSpanProcessor:
    """Wraps a downstream SpanProcessor, redacting on `on_end`.

    Implements the OTel `SpanProcessor` ABC by duck-typing. We intentionally
    do NOT subclass to avoid coupling import order to the OTel SDK install.
    """

    def __init__(self, downstream: Any) -> None:
        self._downstream = downstream

    def on_start(self, span: Any, parent_context: Any = None) -> None:
        try:
            self._downstream.on_start(span, parent_context)
        except Exception as exc:
            _LOG.warning("otel.on_start_failed error=%s", exc)

    def on_end(self, span: Any) -> None:
        try:
            redacted = _RedactedSpan(span)
            self._downstream.on_end(redacted)
        except Exception as exc:
            _LOG.warning("otel.on_end_failed error=%s", exc)

    def shutdown(self) -> None:
        try:
            self._downstream.shutdown()
        except Exception as exc:
            _LOG.warning("otel.shutdown_failed error=%s", exc)

    def force_flush(self, timeout_millis: int = 30000) -> bool:
        try:
            return bool(self._downstream.force_flush(timeout_millis))
        except Exception as exc:
            _LOG.warning("otel.force_flush_failed error=%s", exc)
            return False


__all__ = [
    "PIIRedactionSpanProcessor",
    "_RedactedSpan",
    "_filter_attrs",
    "_filter_resource",
    "_redact_value",
    "_sanitize_exception_event",
    "_sanitize_span_name",
    "_ALLOWED_ATTRS",
    "_ALLOWED_RESOURCE_KEYS",
    "_MAX_VALUE_CHARS",
    "_MAX_SPAN_NAME_CHARS",
]
