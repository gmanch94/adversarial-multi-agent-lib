"""Test helper: RecordingMetricsBackend capturing every metric + span call.

Drives the D-OTEL-4 cardinality fixture test and the per-wire-point assertions
in Slice A. Lives in tests/ (not src/) — production-only metric Protocol stays
in src/adv_multi_agent/core/durable/metrics.py.
"""
from __future__ import annotations

from typing import Any, Mapping


class _RecordingSpan:
    """Span impl that records enter/exit/attrs/exceptions onto a parent backend."""

    def __init__(self, parent: "RecordingMetricsBackend", name: str, tags: dict[str, str]) -> None:
        self._parent = parent
        self._name = name
        self._tags = tags
        self._entered = False
        self._exited = False
        self._exceptions: list[str] = []
        self._attrs: dict[str, Any] = {}

    async def __aenter__(self) -> "_RecordingSpan":
        self._entered = True
        return self

    async def __aexit__(self, exc_type: object, exc: object, tb: object) -> None:
        self._exited = True
        self._parent.spans.append(
            (self._name, frozenset(self._tags.keys()), self._entered, self._exited, tuple(self._exceptions))
        )

    def set_attribute(self, key: str, value: str | int | float | bool) -> None:
        self._attrs[key] = value

    def record_exception(self, exc: BaseException) -> None:
        self._exceptions.append(type(exc).__name__)


class RecordingMetricsBackend:
    """Capture every (name, tag_keys) for counters/gauges/histograms/timings/spans.

    Tag values are intentionally NOT captured — the cardinality fixture asserts
    on tag KEYS only, which is the correct boundary (key set defines cardinality
    dimensions; values define cardinality count).
    """

    def __init__(self) -> None:
        self.counters: list[tuple[str, float, frozenset[str]]] = []
        self.gauges: list[tuple[str, float, frozenset[str]]] = []
        self.histograms: list[tuple[str, float, frozenset[str]]] = []
        self.timings: list[tuple[str, float, frozenset[str]]] = []
        self.spans: list[tuple[str, frozenset[str], bool, bool, tuple[str, ...]]] = []

    def counter(self, name: str, value: int = 1, *, tags: Mapping[str, str] | None = None) -> None:
        self.counters.append((name, float(value), frozenset((tags or {}).keys())))

    def gauge(self, name: str, value: float, *, tags: Mapping[str, str] | None = None) -> None:
        self.gauges.append((name, float(value), frozenset((tags or {}).keys())))

    def histogram(self, name: str, value: float, *, tags: Mapping[str, str] | None = None) -> None:
        self.histograms.append((name, float(value), frozenset((tags or {}).keys())))

    def timing(self, name: str, seconds: float, *, tags: Mapping[str, str] | None = None) -> None:
        self.timings.append((name, float(seconds), frozenset((tags or {}).keys())))

    def span(self, name: str, *, tags: Mapping[str, str] | None = None) -> _RecordingSpan:
        return _RecordingSpan(self, name, dict(tags or {}))

    def tag_keys_by_metric(self) -> dict[str, set[frozenset[str]]]:
        """Return {metric_name: {frozenset(tag_keys), ...}} aggregating all kinds.

        Spans use the span name as the metric_name key for the fixture compare.
        """
        out: dict[str, set[frozenset[str]]] = {}
        for collection in (self.counters, self.gauges, self.histograms, self.timings):
            for name, _value, keys in collection:
                out.setdefault(name, set()).add(keys)
        for sname, skeys, _e, _x, _exc in self.spans:
            out.setdefault(sname, set()).add(skeys)
        return out
