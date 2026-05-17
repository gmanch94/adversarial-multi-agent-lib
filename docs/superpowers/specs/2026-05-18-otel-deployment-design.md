# OTel sibling deployment + PII-redaction SpanProcessor — design

**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Tier:** 1.1 (observability deployment) + 1.7 (PII redaction in observability path)
**Driver:** `docs/production-readiness-gaps.md` §1.1 + §1.7
**Sibling deployments referenced:** `examples/production/durable_postgres/`, `examples/production/cipher_gcp_kms/`

---

## 1. Goal

Ship the OTel reference deployment for the durable subpackage. Library-side `MetricsBackend` Protocol + `NoopMetricsBackend` + 8 wired metric points already shipped (commits `ccdad61` + `464490c`). This spec covers the remaining work:

1. **Library extension:** `MetricsBackend.span(name, *, tags=None)` async-context-manager Protocol method for distributed tracing. `NoopMetricsBackend` ships a no-op `_NoopSpan`. Existing 4-primitive shape preserved.
2. **Additional library wire points** (per gaps doc):
   - lock-acquire path on `resume()` (currently only `start()` wired)
   - lock-pool saturation gauge (sampled by daemon)
   - schema_version distribution gauge (sampled by store)
   - cipher decrypt-failure counter (rotation in-progress signal)
3. **OTel sibling deployment** under `examples/production/durable_postgres_otel/`:
   - `OtelMetricsBackend` implementing `MetricsBackend` (OTLP gRPC exporter)
   - PII-redaction `SpanProcessor` impl
   - Structured-exception sanitizer for `record_exception()`
   - docker-compose adds OTel Collector + Jaeger + Prometheus + Grafana sidecars
   - Grafana dashboard JSON (durable workflow overview)
   - Prometheus alert rules (4 default alerts)
   - CI test: fixture-trace PHI grep gate
   - README: threat model + cost model + setup + operator runbook diff
4. **Runbook updates:** `durable-operations.md` SLO + alert rules sections flip from `REFERENCE-IMPL-PENDING` to `OPERATIONAL`.
5. **Decision rows:** `D-OTEL-1..5` in `docs/decisions.md`.

---

## 2. Threat model

| Asset | Surface | Threat | Mitigation |
|---|---|---|---|
| PHI in checkpoint payloads | OTLP export channel | Exporter ships exception attrs / span attrs containing decrypted request_json fragments | PII-redaction `SpanProcessor` strips known PHI attribute keys; allowlist enforced; exception sanitizer re-serializes with allowed attrs only |
| Tenant boundary | High-cardinality tags | Caller passes `run_id` or `user_id` as tag value → tag-cardinality explosion → backend OOM | Library docstring + runbook forbid per-request PII / per-run tags; cardinality budget documented; CI test asserts no unbounded tag values in wire points |
| OTel Collector compromise | Collector reads PHI-tainted spans | Untrusted collector → exfil channel | Collector runs in same trust boundary as daemon (compose sidecar, internal network only); for prod, runbook directs operator to TLS + mTLS to backend |
| DEK/cipher errors | Decrypt-failure counter | Counter contains key fingerprint → attacker enumerates rotation events | Counter tags allowlist: `workflow_class`, `cipher_backend`, `error_class` only — no key id |
| Fixture-trace test | Test artifacts contain real PHI shapes | Test fixtures could leak | Test uses synthetic Fernet-shaped strings only; grep gate catches `gAAAAA` + DSN-password regex shapes |

PII redaction is **defense-in-depth.** Primary defense remains: library never emits PHI in metric tags or span names. The redaction layer catches caller bugs + accidental `record_exception()` chains.

---

## 3. Locked design choices

### D-OTEL-0: Metrics and spans are orthogonal (advisor clarification)

The 8 existing metric emissions stay alongside the new `span()` wiring. They serve different operator workflows:

| Surface | Drives | Cardinality | Retention |
|---|---|---|---|
| **Metrics** (counter/gauge/histogram) | Dashboards, alert rules, capacity planning | Low (aggregated by tag) | Long (Prometheus default 15d–months) |
| **Spans** (traces) | Causal-chain debugging, latency root-cause, per-request timeline | High (one span tree per run) | Short (Jaeger/Tempo default hours–days) |

`durable.round.latency_seconds` (histogram) → drives p95 alert + dashboard. The round-level span → drives "this specific run paused 3× because the approver wake_at fired late" investigation. Both stay. Operator does NOT delete one.

### D-OTEL-1: `MetricsBackend.span(name)` as async context manager

```python
class MetricsBackend(Protocol):
    # ... existing counter/gauge/histogram/timing ...

    def span(
        self, name: str, *, tags: Mapping[str, str] | None = None
    ) -> "AbstractAsyncContextManager[Span]":
        """Start a span. Async context manager so library can `async with`.

        `Span` is a minimal Protocol with `set_attribute(key, value)` and
        `record_exception(exc)` — same shape as OTel Span subset.
        """
        ...
```

`NoopMetricsBackend` returns `_NoopSpan()` whose `__aenter__/__aexit__` and methods are no-ops. Zero overhead preserved.

**Why async context manager (not sync):** library wire points are all inside `async def` methods; `async with` is idiomatic. OTel SDK supports sync `with span:` from async context, but mixing styles invites operator confusion.

**Why minimal Span surface (not full OTel Span):** decouples library from OTel SDK; lets Datadog / Honeycomb / custom exporters back the Protocol without translation layer.

### D-OTEL-2: PII redaction lives in `SpanProcessor`, not library

The library forbids per-request PII in tags (docstring + runbook). The `SpanProcessor` is **defense-in-depth** for caller bugs + accidental exception attribute leakage.

Allowlist is explicit, denylist is enforced. Allowlist columns:
- `workflow.class`, `workflow.version_hash`, `workflow.schema_version`
- `pause_reason`, `phase`, `cipher_backend`, `lock_backend`
- `status`, `error_class`, `model_fingerprint`
- `round_index`, `attempt_index`, `latency_seconds`
- `duration_ms` (OTel std)

Any other attribute is stripped from `span.attributes` before export. Exception attributes routed through sanitizer.

**Why strip-not-hash:** hashing PHI is still PHI under HIPAA (re-identifiable if attacker has the source dictionary). Strip is the only safe transform.

### D-OTEL-3: Compose sidecars vs daemon-embedded exporter

OTel Collector runs as sibling container in `docker-compose.yml`. Daemon exports via OTLP gRPC to `otel-collector:4317`. Collector handles batching, retry, backend fan-out.

**Why sidecar:** decouples export concerns (backend choice, retry policy, sampling) from daemon. Operator can swap Jaeger → Tempo → Honeycomb by editing collector config alone. Daemon stays exporter-agnostic.

**Why not daemon-direct:** mixing exporter SDK into daemon couples daemon to OTel version churn; sidecar pattern is the OTel-recommended deployment.

### D-OTEL-4: Cardinality budget enforced via runtime-fixture test (advisor revision)

**Original design (rejected):** grep-based static gate. Same shape that broke twice (M-PC-1, H-IND-1) — regex against `self._metrics.*(tags=...)` doesn't catch `tags={"workflow": foo}` where `foo = run_id` two lines up.

**Locked design:** `tests/unit/durable/test_metrics_cardinality_fixture.py` runs a synthetic durable workflow through a `RecordingMetricsBackend` that captures every `(metric_name, frozenset(tag_keys))` pair emitted. Asserts the captured set equals an explicit fixture dict. New wire-point PRs must update the fixture explicitly — forcing reviewer attention on every cardinality change.

Catches the failure mode: PR adds `tags={"run_id": run_id}` → fixture mismatch → test fails before merge. Runtime evidence beats regex (cf. CLAUDE.md test-shape pitfall).

### D-OTEL-5: Reference deployment is opt-in dependency

`examples/production/durable_postgres_otel/requirements.in` pins:
- `opentelemetry-api`
- `opentelemetry-sdk`
- `opentelemetry-exporter-otlp-proto-grpc`

These do NOT bleed into the library's `pyproject.toml`. Library stays dependency-free. Operator pays the OTel cost only when they choose the OTel sibling.

---

## 4. File layout

```
examples/production/durable_postgres_otel/
  __init__.py
  README.md                           threat model + setup + operator diff vs durable_postgres
  pyproject.toml                      opt-in deps pin
  requirements.in / requirements.txt  hashed + pinned
  docker-compose.yml                  daemon + postgres + otel-collector + jaeger + prometheus + grafana
  Dockerfile                          inherits hardening from durable_postgres + adds OTel deps
  otel_backend.py                     OtelMetricsBackend + _OtelSpan
  pii_redaction_span_processor.py    PII-redaction SpanProcessor + exception sanitizer
  collector-config.yml                OTel Collector pipeline
  prometheus.yml                      Prometheus scrape config
  alerts.yml                          4 default alert rules
  grafana/
    dashboards/
      durable-workflow-overview.json  pre-built dashboard
    provisioning/
      dashboards.yml
      datasources.yml
  daemon.py                           thin wrapper over durable_postgres.daemon — adds OTel init
  smoke_test.py                       boots stack, fires one workflow, asserts metrics + spans + redaction
  tests/
    __init__.py
    test_otel_backend.py              unit: counter/gauge/histogram/timing/span emission shapes
    test_pii_redaction.py             unit: SpanProcessor strips PHI, exception sanitizer
    test_phi_grep_gate.py             integration: record fixture traces, grep for PHI shapes
  scripts/
    check_cardinality.sh              CI gate: tag values are allowlisted
```

Library-side changes:
```
src/adv_multi_agent/core/durable/
  metrics.py                          +span() Protocol method, +_NoopSpan
  workflow.py                         wire span around _execute_round; wire lock-acquire on resume()
  store.py                            schema_version gauge sample (if postgres store)
  cipher.py / encryption.py           cipher decrypt-failure counter
```

Tests:
```
tests/unit/durable/
  test_metrics_span_protocol.py       4 new tests: noop span no-op; structural typing
  test_workflow_span_wiring.py        2 new tests: span fires per round, around resume()
  test_decrypt_failure_counter.py     2 new tests: counter fires on InvalidToken, KmsDecryptError
```

---

## 5. Invariants enforced (think-first protocol)

1. **Cardinality discipline.** Every `self._metrics.*(tags=...)` call passes only allowlisted low-cardinality tag values. Enforced by `scripts/check_cardinality.sh` in CI.
2. **PII boundary.** PHI never appears in metric tag values, span names, or span attributes (post-redaction). Enforced by `pii_redaction_span_processor` + `test_phi_grep_gate.py`.
3. **Zero-overhead Noop.** `NoopMetricsBackend.span()` returns a no-op async context manager whose `__aenter__/__aexit__` cost is ≤2µs. Enforced by perf test in `test_metrics_span_protocol.py`.
4. **Telemetry never breaks the workflow.** `OtelMetricsBackend` methods swallow exceptions, log internally. Enforced by `test_otel_backend.py::test_exporter_failure_does_not_propagate`.
5. **Library stays dependency-free.** `pyproject.toml` of the library unchanged. OTel deps confined to `examples/production/durable_postgres_otel/pyproject.toml`. Enforced by `tox` / pre-PR gate run.

## 6. Attack surface

| Path | Surface | Enforcement |
|---|---|---|
| OTLP export → Collector | gRPC TLS or in-cluster network | Compose internal network; prod runbook directs mTLS |
| Collector → backend (Jaeger/Tempo) | Collector config | Collector config TLS-only for prod; runbook checklist |
| Grafana datasource | Prometheus + Tempo URLs | Provisioned via file; no admin password in compose for prod (runbook directs SSO) |
| Metric tag values | Library wire points | `scripts/check_cardinality.sh` CI gate |
| Span attributes | `SpanProcessor` allowlist | Strip not on allowlist; CI fixture-trace test |
| `record_exception()` | Exception sanitizer | Re-serialize with allowlist attrs; original exception class name preserved |

## 7. Failure modes

| Failure | Behavior |
|---|---|
| OTel Collector down | `OtelMetricsBackend` swallows export errors. Daemon logs WARN once per N seconds. Workflow continues. |
| OTel SDK exception during export | Swallow + log. Workflow never breaks on telemetry. |
| Grafana / Prometheus down | Pure observability loss. Daemon unaffected. |
| PHI in metric tag value (caller bug) | CI cardinality gate catches before merge. Runtime: tag still exported (defense-in-depth: SpanProcessor only filters spans, not metrics — metrics PHI is unrecoverable post-export). |
| PHI in span attribute (`record_exception` chain) | SpanProcessor strips before export. |
| OTel deps version conflict | Sibling pyproject.toml isolation; doesn't affect library install. |

## 8. Operator actions outside the diff (durable items)

- **Provision Grafana admin credential** (runbook §X — replace compose default `admin/admin` for prod)
- **Configure mTLS for OTel Collector → backend** (runbook §Y)
- **Set retention policy on Tempo/Jaeger** for trace data (PHI residency)
- **Document chosen backend in `SECURITY_MODEL.md` §observability** (Jaeger / Tempo / Honeycomb / Datadog)
- **Enable Prometheus alert webhook → PagerDuty / Slack** (alerts.yml ships rules; routing is operator-owned)

All five become rows in a new `docs/runbooks/otel-operations.md` checklist file (per CLAUDE.md operator-actions rule).

## 9. Test plan

| Test | Type | Asserts |
|---|---|---|
| `test_metrics_span_protocol.py::test_noop_span_zero_overhead` | unit | 1000 noop span enter/exit < 5ms total |
| `test_metrics_span_protocol.py::test_noop_span_records_exception_silently` | unit | `record_exception` on noop span doesn't raise |
| `test_workflow_span_wiring.py::test_span_per_round` | unit | Span emitted around each `_execute_round` call |
| `test_workflow_span_wiring.py::test_lock_acquire_metrics_on_resume` | unit | Lock-acquire latency + failure counter fire on resume path |
| `test_decrypt_failure_counter.py::test_invalid_token_increments_counter` | unit | Fernet `InvalidToken` → counter+1 |
| `test_decrypt_failure_counter.py::test_kms_error_increments_counter` | unit | `KmsDecryptError` → counter+1 |
| `test_otel_backend.py::test_counter_increments_meter` | unit | `OtelMetricsBackend.counter` → OTel Counter.add |
| `test_otel_backend.py::test_exporter_failure_does_not_propagate` | unit | Mock exporter raises → backend swallows |
| `test_otel_backend.py::test_span_records_attributes` | unit | `set_attribute` lands on OTel Span |
| `test_pii_redaction.py::test_phi_attribute_stripped` | unit | Span with `patient.id` → attribute removed pre-export |
| `test_pii_redaction.py::test_allowlisted_attribute_preserved` | unit | `workflow.class` → preserved |
| `test_pii_redaction.py::test_exception_sanitizer_keeps_class_drops_message` | unit | Exception with PHI in args → only class name + allowlisted attrs survive |
| `test_phi_grep_gate.py::test_fixture_trace_has_no_phi_shapes` | integration | Recorded trace JSON: no `gAAAAA` token, no DSN passwords, no PHI column names |

13 new tests. Target: 698 → 711 passing.

## 10. Decision rows

- **D-OTEL-1** — `MetricsBackend.span(name)` as async context manager; minimal `Span` Protocol.
- **D-OTEL-2** — PII redaction via `SpanProcessor` with explicit allowlist; defense-in-depth on top of library cardinality discipline.
- **D-OTEL-3** — OTel Collector as compose sidecar (not daemon-embedded); operator chooses backend via collector config.
- **D-OTEL-4** — `scripts/check_cardinality.sh` CI gate prevents per-request PII in tag values.
- **D-OTEL-5** — OTel deps confined to sibling `pyproject.toml`; library stays dependency-free.

## 11. Out of scope (explicit non-goals)

- Log-export to OTel (logs stay in stdout/journal per `durable-operations.md` §allowlist)
- Metrics → Prometheus push-gateway (use OTLP → Collector → Prometheus remote-write instead)
- Custom Grafana plugins
- Backend-specific dashboards (Tempo / Honeycomb / Datadog variants); ship Grafana+Prometheus reference only
- Sampling policy beyond OTel default (operator owns)
- k8s manifests (Tier 1.2 lane; OTel sidecar pattern is k8s-compatible by design)

## 11.5. Slicing plan (advisor revision)

Per advisor: don't ship 5–6d as one mega-commit. Three independently revertable slices, each with its own audit checkpoint.

### Slice A — Library extension (1d, 698→706 tests)
- `MetricsBackend.span()` Protocol method + `_NoopSpan`
- `RecordingMetricsBackend` test helper (drives D-OTEL-4 fixture test)
- 4 new wire points: lock-acquire on `resume()`, lock-pool saturation gauge, schema_version distribution gauge, cipher decrypt-failure counter
- Span wiring: one span around each `_execute_round`-equivalent call (start + resume paths)
- ~8 new tests (incl. cardinality fixture)
- Single commit. Ships clean. Sibling shell (Slice B) imports the new Protocol.

### Slice B — OTel sibling shell (2d, +smoke tests)
- `examples/production/durable_postgres_otel/` skeleton
- `OtelMetricsBackend` + `_OtelSpan` implementing Slice-A Protocols
- `pii_redaction_span_processor.py` + exception sanitizer
- `requirements.in/.txt` (opt-in OTel deps)
- `docker-compose.yml` adds collector + jaeger + prometheus + grafana
- `Dockerfile` inherits durable_postgres hardening
- `daemon.py` thin wrapper enabling OTel init
- `smoke_test.py` — boots stack, fires one workflow, asserts metrics + spans + redaction
- Unit tests: `test_otel_backend.py`, `test_pii_redaction.py` (~6 tests)
- Cycle-11a audit on Slice B surface before commit (cipher_gcp_kms cadence)

### Slice C — Operational dressing (1.5d)
- Grafana dashboard JSON (durable workflow overview)
- 4 Prometheus alert rules (p95 latency, decrypt failure rate, pause-vs-resume ratio, lock-pool saturation)
- Collector config tuning + Prometheus scrape config refinement
- `README.md` (threat model + cost model + setup + operator diff vs durable_postgres)
- `docs/runbooks/otel-operations.md` (5 operator-checklist rows)
- Runbook updates: `durable-operations.md` SLOs flip REFERENCE-IMPL-PENDING → OPERATIONAL
- `tests/test_phi_grep_gate.py` integration test
- `D-OTEL-1..5` rows in `decisions.md`
- Cycle-11b audit on full surface

Each slice is one PR-equivalent commit chain pushed direct-to-main per CLAUDE.md ship-flow. Slice B+C may share an audit if A is uneventful; default to three audits.

## 12. Effort

- Library extension (span Protocol + 4 new wire points + tests): 1d
- OtelMetricsBackend + tests: 1d
- PII redaction SpanProcessor + exception sanitizer + tests: 1d
- Compose stack + collector config + Prometheus + Grafana provisioning: 1d
- Grafana dashboard JSON + alert rules: 0.5d
- README + threat model + runbook updates: 0.5d
- CI cardinality gate + PHI grep gate: 0.5d
- Cycle-11 security audit + drain: 0.5d

**Total: 5–6 days.** Per autonomy: secure (PII redaction lands alongside, not after) + durable (alert rules + dashboards survive operator turnover) + scalable (Protocol stays plug-replaceable; sibling pattern proven by `cipher_gcp_kms`).
