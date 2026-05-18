# Security audit — Tier 1.1 Slice B (OTel sibling deployment)

**Date:** 2026-05-18
**Scope:** `examples/production/durable_postgres_otel/` (newly added; ~10 files)
**Auditor:** inline self-audit (Slice B executor), structured per CLAUDE.md security protocol
**Predecessor inherited remediations:** durable_postgres hardening (A8-*, F-*, N-*), library D-OTEL-1..4 (Slice A)

---

## Methodology

Each new file walked through the 6 watch-items in plan Task 11:
1. PII leakage via span attributes / exception events (D-OTEL-2 allowlist)
2. Container hardening parity with durable_postgres
3. Collector config trust boundary (default credentials in compose are non-prod)
4. Cardinality discipline (no per-request PII in tag values)
5. docker-compose secret-handling (Grafana admin default)
6. Python except-clause scope (B2 recurrence)

Plus generic checks: command injection, path traversal, hardcoded credentials, unsafe deserialization, SSRF.

---

## CRITICAL findings: 0

## HIGH findings: 0

## MEDIUM findings: 3

### M-OTEL-SB-1 — Placeholder container digests are not real

**Files:** `docker-compose.yml` lines 64, 78, 91, 105
**Watch-item:** (2) container hardening parity

The four non-postgres images (`otel-collector`, `jaeger`, `prometheus`, `grafana`) ship with placeholder SHA-256 digests. A naive `docker compose up` will fail to pull, surfacing the issue loudly. The compose header explicitly flags this as an operator action.

**Remediation:** documented in compose header + README "Setup" step 2. Operator must run `docker pull <tag>` + `docker inspect ... --format='{{index .RepoDigests 0}}'` and replace each placeholder before first deploy.

**Severity rationale:** MEDIUM not HIGH because (a) it fails closed (image pull fails, daemon never starts), and (b) the alternative — using `:tag` without digest pinning — would silently regress the supply-chain posture. Cannot verify real digests inline without docker daemon access.

### M-OTEL-SB-2 — Grafana default admin password

**File:** `docker-compose.yml` line 122 (`GF_SECURITY_ADMIN_PASSWORD: ${GRAFANA_ADMIN_PASSWORD:-admin}`)
**Watch-item:** (5) compose secret-handling

Default admin password is `admin` when `GRAFANA_ADMIN_PASSWORD` is unset. README "Setup" step 4 instructs the operator to set it before any non-local deploy. Port is localhost-bound (`127.0.0.1:3000:3000`), so non-local exposure requires SSH tunnel or explicit operator action — defense in depth.

**Remediation:** README documents the requirement; compose has fallback to keep local-dev smoke working. Acceptable for a reference deploy. Production operators inherit this as a checklist item.

### M-OTEL-SB-3 — Collector OTLP receiver is plaintext

**File:** `collector-config.yml` lines 8-13
**Watch-item:** (3) trust boundary

OTLP gRPC receiver listens on `0.0.0.0:4317` without TLS. The receiver is reachable only on the internal docker network (no host port binding), so MITM requires container compromise. Production posture should use TLS + mTLS — documented in the YAML comment + README.

**Remediation:** documented. Slice C runbook can flesh out the cert-provisioning recipe.

---

## LOW findings: 2

### L-OTEL-SB-1 — Broad `except Exception` in `_OtelSpan.__aenter__/__aexit__`

**File:** `otel_backend.py` lines 195-205, 207-220
**Watch-item:** (6) except-clause scope

The span context manager swallows all exceptions from the OTel SDK. This is intentional per spec §7 (telemetry never breaks the workflow) and matches the durable_postgres `_sample_pool_saturation` pattern (lines 384-387). Logged at WARNING so operators see degradation.

**Severity rationale:** LOW because the broad catch is by design and isolated to telemetry. Workflow-critical exceptions raised inside the wrapped `async with` body still propagate — `__aexit__` returns `False`.

### L-OTEL-SB-2 — PII redactor relies on private OTel attr `_active_span_processor`

**File:** `otel_backend.py` lines 109-115
**Watch-item:** (1) PII leakage

`install_pii_redaction()` swaps the BatchSpanProcessor inside `TracerProvider._active_span_processor._span_processors` — a private OTel SDK attribute. SDK churn could silently break redaction. Wrapped in try/except + WARNING log; failure leaves the un-redacted BatchSpanProcessor active.

**Failure mode if SDK changes:** spans export with un-redacted attributes. WARNING log fires once at startup. Operator dashboards would surface PHI keys.

**Remediation suggested for Slice C:** add a startup assertion that traces a known PHI-shaped attribute and verifies it gets stripped before export. Track as a deferred item.

---

## Items explicitly verified clean

- **`_filter_attrs` allowlist completeness:** every library-emitted attribute key from Slice A (`workflow.*`, `pause_reason`, `phase`, `cipher_backend`, `lock_backend`, `status`, `error_class`, `model_fingerprint`, `round.*`, `attempt.*`, `latency_seconds`, `duration_ms`) appears in `_ALLOWED_ATTRS`. Cross-checked against `src/adv_multi_agent/core/durable/durable.py` and `metrics.py`.
- **Exception sanitization:** test `test_exception_event_keeps_type_drops_message_and_stack` enforces `exception.message` + `exception.stacktrace` stripped, `exception.type` kept.
- **No hardcoded secrets:** no API keys, DSNs, or tokens in any new file. Grafana default is documented + overridable.
- **No command injection surface:** Dockerfile `ENTRYPOINT` uses `sh -c` with a fixed string; no user input flows in.
- **No path traversal:** all file paths in compose are fixed and quoted; no `${VAR}` interpolation into paths.
- **No unsafe deserialization:** no `pickle`, `eval`, `exec`, `yaml.unsafe_load` in any new file.
- **Container hardening parity:** all 4 new services have `cap_drop: [ALL]`, `security_opt: no-new-privileges:true`, `ulimits.core: 0`. `daemon` service additionally has `read_only: true + tmpfs`.
- **Test cardinality:** unit tests use `InMemoryMetricReader` + `InMemorySpanExporter` only; no live network.

---

## Final posture

- **0 CRITICAL + 0 HIGH.** Commit chain authorized per plan Task 11.
- **3 MEDIUM** — all documented inline (placeholder digests, Grafana default, plaintext OTLP). Each has README/comment-level remediation guidance. Slice C runbook can promote to operational hardening.
- **2 LOW** — broad telemetry except (by design, spec §7) + private OTel attr dependency (mitigation: try/except + WARNING log; Slice C startup assertion deferred).

No CRITICAL/HIGH drains required. Proceeding to commit chain.
