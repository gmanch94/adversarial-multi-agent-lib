# Plan — Slice B: OTel sibling deployment shell

**Spec:** `docs/superpowers/specs/2026-05-18-otel-deployment-design.md`
**Predecessor:** Slice A (commit `52388a4`) — span() Protocol + wire points
**Slice scope:** `examples/production/durable_postgres_otel/` skeleton + `OtelMetricsBackend` + PII redaction + smoke test + compose stack. NO Grafana dashboards / alert rules / runbook updates (Slice C).
**Target:** ~12-16 new files, ~6 new unit tests, library unchanged, ruff+mypy clean, cycle-11a audit before commit chain.

---

## Task order

### Task 0 — Scaffold + opt-in deps

**New files:**
- `examples/production/durable_postgres_otel/__init__.py` (empty)
- `examples/production/durable_postgres_otel/pyproject.toml` — sibling pkg metadata (mirrors `cipher_gcp_kms/pyproject.toml` structure)
- `examples/production/durable_postgres_otel/requirements.in`:
  ```
  opentelemetry-api>=1.27.0,<2.0
  opentelemetry-sdk>=1.27.0,<2.0
  opentelemetry-exporter-otlp-proto-grpc>=1.27.0,<2.0
  ```
- `examples/production/durable_postgres_otel/requirements.txt` — generated via `pip-compile --generate-hashes` (operator-checklist OK if not generated in this slice; placeholder file with TODO header is acceptable since CI doesn't install OTel deps)

Document in README that this is opt-in; library has no OTel dep.

### Task 1 — `OtelMetricsBackend` + `_OtelSpan`

**File:** `examples/production/durable_postgres_otel/otel_backend.py` (new)

Implements `MetricsBackend` Protocol from `core/durable/metrics.py`:

```python
class OtelMetricsBackend:
    """OTel-backed MetricsBackend. Wraps OTel Meter + Tracer.

    Swallows all exporter exceptions per spec §7 (telemetry never breaks workflow).
    """
    def __init__(self, *, service_name: str, otlp_endpoint: str = "otel-collector:4317"):
        # Init MeterProvider + TracerProvider + OTLP exporters
        # Build counter/gauge/histogram instruments lazily (dict cache)
        ...

    def counter(self, name, value=1, *, tags=None):
        try:
            self._counter(name).add(value, attributes=dict(tags or {}))
        except Exception as exc:
            _LOG.warning("otel.counter_failed", extra={"name": name, "error": str(exc)})

    def gauge(self, name, value, *, tags=None): ...  # uses ObservableGauge with callback OR up-down counter
    def histogram(self, name, value, *, tags=None): ...
    def timing(self, name, seconds, *, tags=None): self.histogram(name, seconds, tags=tags)

    def span(self, name, *, tags=None):
        return _OtelSpan(self._tracer, name, tags or {})


class _OtelSpan:
    """Async context manager backing MetricsBackend.span()."""
    def __init__(self, tracer, name, tags):
        self._tracer = tracer
        self._name = name
        self._tags = tags
        self._span = None
        self._cm = None
    async def __aenter__(self):
        self._cm = self._tracer.start_as_current_span(self._name, attributes=self._tags)
        self._span = self._cm.__enter__()
        return self
    async def __aexit__(self, exc_type, exc, tb):
        if exc:
            try: self._span.record_exception(exc)
            except Exception: pass
        self._cm.__exit__(exc_type, exc, tb)
        return False
    def set_attribute(self, key, value):
        try: self._span.set_attribute(key, value)
        except Exception: pass
    def record_exception(self, exc):
        try: self._span.record_exception(exc)
        except Exception: pass
```

**Gauge note:** OTel SDK has no direct "set" gauge primitive; use `UpDownCounter` with diff-tracking OR `ObservableGauge` with callback. Pick `UpDownCounter` + cached last-value-per-tag-set for simplicity. Document the choice in module docstring.

### Task 2 — PII-redaction SpanProcessor

**File:** `examples/production/durable_postgres_otel/pii_redaction_span_processor.py` (new)

```python
_ALLOWED_ATTRS = frozenset({
    "workflow.class", "workflow.version_hash", "workflow.schema_version",
    "pause_reason", "phase", "cipher_backend", "lock_backend",
    "status", "error_class", "model_fingerprint",
    "round.index", "round.converged", "round.paused",
    "attempt.index", "latency_seconds", "duration_ms",
    # OTel standard
    "service.name", "service.version",
    "telemetry.sdk.name", "telemetry.sdk.version", "telemetry.sdk.language",
    "otel.scope.name", "otel.scope.version",
    "span.kind",
})


class PIIRedactionSpanProcessor(SpanProcessor):
    """OnEnd: strip non-allowlisted attributes from span.attributes
    and sanitize exception events before export."""
    def __init__(self, downstream: SpanProcessor):
        self._downstream = downstream

    def on_start(self, span, parent_context=None):
        self._downstream.on_start(span, parent_context)

    def on_end(self, span):
        # Build new ReadableSpan with filtered attributes
        # Strip events that aren't in allowlist; sanitize 'exception' events
        sanitized = _redact_span(span)
        self._downstream.on_end(sanitized)

    def shutdown(self): self._downstream.shutdown()
    def force_flush(self, timeout_millis=30000): return self._downstream.force_flush(timeout_millis)


def _redact_span(span):
    """Return wrapped span with allowlisted attributes + sanitized exception events only."""
    # Approach: subclass ReadableSpan-equivalent; or construct a SimpleNamespace duck-typed for OTLP exporter
    ...


def _sanitize_exception_event(event):
    """Drop 'exception.message' and 'exception.stacktrace'; keep 'exception.type' only.
    Stacktrace + message can contain PHI (formatted request_json fragments)."""
    ...
```

Implementation note: OTel `ReadableSpan` is immutable — to filter attributes, either (a) use `BatchSpanProcessor` with a custom span subclass (complex), or (b) build a `ProxyReadableSpan` that re-implements the attribute accessor reading from a filtered dict. Pick (b). Cite the design in the module docstring.

### Task 3 — daemon.py thin wrapper

**File:** `examples/production/durable_postgres_otel/daemon.py` (new)

Mirrors `examples/production/durable_postgres/daemon.py` structure but adds OTel init at top:

```python
from .otel_backend import OtelMetricsBackend
from .pii_redaction_span_processor import PIIRedactionSpanProcessor

def _build_metrics():
    backend = OtelMetricsBackend(
        service_name=os.environ.get("OTEL_SERVICE_NAME", "durable-workflow"),
        otlp_endpoint=os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "otel-collector:4317"),
    )
    # Wrap TracerProvider's span processor in PIIRedactionSpanProcessor
    backend.install_pii_redaction()
    return backend

# Reuse durable_postgres.daemon's workflow_factory + handler — pass metrics= into DurableWorkflow
```

Minimize duplication: import the durable_postgres handler module and inject `metrics=` via a small wrapper. If that's too invasive, copy the daemon file outright and document the divergence in a header comment.

### Task 4 — docker-compose stack

**File:** `examples/production/durable_postgres_otel/docker-compose.yml` (new)

Services:
- `postgres` (same image+config as `durable_postgres/docker-compose.yml`, digest-pinned)
- `daemon` (this directory's Dockerfile build, depends_on postgres + otel-collector)
- `otel-collector` (`otel/opentelemetry-collector-contrib:0.103.0` digest-pinned; mounts `collector-config.yml`)
- `jaeger` (`jaegertracing/all-in-one:1.59` digest-pinned; for trace viewer)
- `prometheus` (`prom/prometheus:v2.54.0` digest-pinned; scrapes collector's `/metrics` endpoint)
- `grafana` (`grafana/grafana:11.1.0` digest-pinned; provisioned datasources; default admin password = `admin` with prod-warning comment)

Hardening per CLAUDE.md / durable_postgres pattern:
- `no-new-privileges`, `cap_drop: [ALL]`, `read_only: true` where possible
- `ulimits.core: 0`
- Internal network only; no host ports for postgres / collector

### Task 5 — collector-config.yml + prometheus.yml

**Files:**
- `examples/production/durable_postgres_otel/collector-config.yml` — receivers `otlp` (grpc 4317); processors `batch`; exporters `jaeger` (traces), `prometheus` (metrics on `:8889`); pipelines wiring them
- `examples/production/durable_postgres_otel/prometheus.yml` — scrape `otel-collector:8889`

### Task 6 — Dockerfile

**File:** `examples/production/durable_postgres_otel/Dockerfile` (new)

Mirror `durable_postgres/Dockerfile` hardening (non-root, read-only-rootfs-compatible, digest-pinned base, wheel-only install). Add the OTel deps install layer. Inherits Slice A `MetricsBackend.span()` from library install.

### Task 7 — smoke_test.py

**File:** `examples/production/durable_postgres_otel/smoke_test.py` (new)

Asserts (impl correctness only; live API not called):
1. `OtelMetricsBackend` instantiates without raising
2. `counter`/`gauge`/`histogram`/`timing` swallow exporter exceptions (mock OTLP endpoint set to invalid)
3. `span("name") async with` exits cleanly
4. `PIIRedactionSpanProcessor.on_end` strips a non-allowlisted attribute from a recorded span
5. `_sanitize_exception_event` drops message + stacktrace, keeps type

### Task 8 — Unit tests

**Files:**
- `examples/production/durable_postgres_otel/tests/__init__.py`
- `examples/production/durable_postgres_otel/tests/test_otel_backend.py` (~4 tests):
  - `test_counter_increments_meter` (uses InMemoryMetricReader)
  - `test_histogram_records_value`
  - `test_exporter_failure_does_not_propagate` (mock OTLP exporter raises)
  - `test_span_records_attributes_and_exception`
- `examples/production/durable_postgres_otel/tests/test_pii_redaction.py` (~4 tests):
  - `test_phi_attribute_stripped`
  - `test_allowlisted_attribute_preserved`
  - `test_exception_event_keeps_type_drops_message_and_stack`
  - `test_non_exception_event_preserved`

Tests use OTel `InMemoryMetricReader` + `InMemorySpanExporter` from `opentelemetry-sdk` test utilities — no live network calls.

**Gating decision:** tests live under `examples/production/durable_postgres_otel/tests/` and are skipped by default in the library's main pytest run (CI doesn't install OTel deps). Document in README how to run them locally:
```
cd examples/production/durable_postgres_otel
pip install -e . -r requirements.txt
pytest
```

Smoke test for `pytest` exclusion: add `pyproject.toml`-level test exclusion or use a `conftest.py` `collect_ignore_glob` in `tests/conftest.py` to skip `examples/production/durable_postgres_otel/`.

### Task 9 — README

**File:** `examples/production/durable_postgres_otel/README.md` (new)

Sections (mirror `cipher_gcp_kms/README.md` structure):
1. What this is (sibling deployment adding OTel observability to durable_postgres)
2. Threat model (per spec §2 — copy the table)
3. PII boundary (per D-OTEL-2 — allowlist, redaction posture, residual risks)
4. Cost model (compose: 4 extra containers = ~500MB RAM; OTLP gRPC bandwidth ~10KB/run typical)
5. Setup (compose up, env vars, default Grafana admin warning)
6. Wire-point inventory (the 8 metrics + spans Slice A wired, plus the 4 new ones)
7. Operator runbook diff vs `durable_postgres` (4 net-new operator concerns: collector backpressure, Grafana auth, retention policy, mTLS for prod)
8. Cardinality budget (refer to library D-OTEL-4 fixture test)
9. Known gaps deferred to Slice C: alert rules, Grafana dashboard, runbook flip

### Task 10 — Conftest test-exclusion in main suite

**File:** `tests/conftest.py` (edit) OR root-level `pyproject.toml` `[tool.pytest.ini_options]` `norecursedirs`

Either:
- Add `examples/production/durable_postgres_otel` to `pyproject.toml` `[tool.pytest.ini_options].norecursedirs`
- OR add `collect_ignore_glob = ["examples/production/durable_postgres_otel/*"]` to `tests/conftest.py`

Verify: `pytest --collect-only -q | wc -l` doesn't include OTel example tests.

### Task 11 — Cycle-11a security audit (pre-commit)

Spawn `Agent` with `subagent_type=general-purpose` or use `Skill` invoking `security-audit` on `examples/production/durable_postgres_otel/` ONLY (do NOT re-audit durable_postgres). Audit prompt:

> Security audit `examples/production/durable_postgres_otel/` (newly added OTel sibling deployment). Stack: OpenTelemetry Python SDK + OTLP gRPC + asyncpg-backed durable_postgres daemon. Specific watch-items inherited from prior cycles: (1) PII leakage via span attributes / exception events (D-OTEL-2 allowlist), (2) container hardening parity with durable_postgres (non-root, read-only-rootfs, cap_drop, no-new-privileges, digest-pinned images, ulimits.core: 0), (3) collector config trust boundary (default credentials in compose are non-prod), (4) cardinality discipline (no per-request PII in tag values), (5) docker-compose secret-handling (Grafana admin default), (6) Python except-clause scope (B2 recurrence). Report CRITICAL/HIGH/MEDIUM/LOW with file+line citations + remediation hints. Under 600 words.

Drain CRITICAL + HIGH inline before commit. MEDIUM/LOW can backlog.

Audit report goes to `docs/security-audits/2026-05-18-otel-slice-b-sweep.md`.

### Task 12 — Verify + commit chain

Pre-PR gate (library tests, NOT OTel example tests):
```
python scripts/check_no_secrets.py
python -m ruff check .
python -m mypy src
python -m pytest -q
```

Library test count: 710 (no change from Slice A).

Commit chain (3-5 commits, semantic grouping):
1. `feat(otel): Slice B scaffold + OtelMetricsBackend + _OtelSpan`
2. `feat(otel): PII-redaction SpanProcessor + exception sanitizer`
3. `feat(otel): docker-compose stack + collector config + daemon wrapper`
4. `test(otel): 8 unit tests + smoke test`
5. `docs(otel): README + cycle-11a audit + any HIGH drains`

Push after the chain.

---

## Sanity checks before declaring done

- [ ] Library `pyproject.toml` UNCHANGED
- [ ] `python -m pytest -q` still reports 710 (OTel example tests excluded from main suite)
- [ ] All docker images digest-pinned
- [ ] `docker-compose config` parses cleanly (no syntax error)
- [ ] Cycle-11a audit ran; 0 CRIT + 0 HIGH at commit time
- [ ] Mypy + ruff clean on every NEW file (run them with `python -m ruff check examples/production/durable_postgres_otel/`)

## Not in this slice

- Grafana dashboard JSON (Slice C)
- Prometheus alert rules YAML (Slice C)
- `docs/runbooks/otel-operations.md` (Slice C)
- Runbook `durable-operations.md` flip REFERENCE-IMPL-PENDING → OPERATIONAL (Slice C)
- Decision rows D-OTEL-1..5 (Slice C)
- PHI grep gate integration test (Slice C — needs the full stack to record fixture traces)

## Commit-message hygiene reminder

PowerShell + bash both choke on `&`, `>`, `<`, `|`, `&&` in `-m "..."`. Past burns logged in `CLAUDE.md`. Use words (`and`, `gt`, `lt`) or escape.
