# Plan — Slice C: operational dressing for OTel deployment

**Spec:** `docs/superpowers/specs/2026-05-18-otel-deployment-design.md`
**Predecessors:**
- Slice A: commit `52388a4` (library extension)
- Slice B: commits `4f97968`..`9b8a669` (sibling shell + audit)

**Slice scope:** Grafana dashboard + Prometheus alert rules + collector tuning + operator runbook + decision rows + PHI grep gate + runbook flip + closing audit (cycle-11b).

**Target:** ~8 new files + ~5 edited docs + 1 PHI integration test + cycle-11b audit + NEXT_SESSION refresh.

---

## Task order

### Task 1 — Grafana dashboard JSON

**File:** `examples/production/durable_postgres_otel/grafana/dashboards/durable-workflow-overview.json` (new)

Pre-built Grafana dashboard sourced from Prometheus datasource. Panels (8 minimum):

1. **Workflow starts per minute** — `rate(durable_workflow_start_total[1m])` by `workflow`
2. **Pause rate per workflow per reason** — `rate(durable_workflow_pause_total[5m])` by `workflow, pause_reason`
3. **p50/p95/p99 round latency** — `histogram_quantile(0.95, sum by (le, workflow) (rate(durable_round_latency_seconds_bucket[5m])))`
4. **Lock acquire failures per minute** — `rate(durable_lock_acquire_failed_total[1m])` by `phase`
5. **Lock acquire latency (p95)** — `histogram_quantile(0.95, sum by (le, phase) (rate(durable_lock_acquire_latency_seconds_bucket[5m])))`
6. **Lock pool saturation** — `durable_lock_pool_saturation` gauge by `pool`
7. **Cipher decrypt failure rate** — `rate(durable_cipher_decrypt_failed_total[5m])` by `cipher_backend, error_class`
8. **Budget tokens + USD** — `durable_budget_tokens_in` + `durable_budget_tokens_out` + `durable_budget_usd_spent` gauges

Provisioning files:
- `examples/production/durable_postgres_otel/grafana/provisioning/dashboards.yml`
- `examples/production/durable_postgres_otel/grafana/provisioning/datasources.yml` — Prometheus datasource pointing at `prometheus:9090`

Mount in `docker-compose.yml` (edit Slice B's compose):
```yaml
grafana:
  volumes:
    - ./grafana/provisioning:/etc/grafana/provisioning:ro
    - ./grafana/dashboards:/var/lib/grafana/dashboards:ro
```

### Task 2 — Prometheus alert rules

**File:** `examples/production/durable_postgres_otel/alerts.yml` (new)

4 default alerts per spec §1:

```yaml
groups:
- name: durable-workflow
  interval: 30s
  rules:
  - alert: DurableHighRoundLatency
    expr: histogram_quantile(0.95, sum by (le) (rate(durable_round_latency_seconds_bucket[5m]))) > 30
    for: 10m
    labels: {severity: warning}
    annotations:
      summary: p95 round latency above 30s for 10m
      runbook: see docs/runbooks/durable-operations.md SLO section
  - alert: DurableCipherDecryptFailureSpike
    expr: rate(durable_cipher_decrypt_failed_total[5m]) > 0.1
    for: 5m
    labels: {severity: critical}
    annotations:
      summary: Cipher decrypt failure rate above 0.1/s
      runbook: rotation in-progress OR key compromise - see otel-operations.md
  - alert: DurablePauseResumeImbalance
    expr: (rate(durable_workflow_pause_total[1h]) - rate(durable_workflow_start_total[1h])) > 0
    for: 30m
    labels: {severity: warning}
    annotations:
      summary: Pauses outpacing starts; runs accumulating in paused state
      runbook: check scheduler health + approver SLA
  - alert: DurableLockPoolNearSaturation
    expr: durable_lock_pool_saturation > 0.85
    for: 5m
    labels: {severity: warning}
    annotations:
      summary: Lock pool above 85% saturation
      runbook: scale daemon replicas OR investigate stuck runs
```

Wire into `prometheus.yml` (edit Slice B's prometheus config):
```yaml
rule_files:
  - /etc/prometheus/alerts.yml
```

And compose volume mount.

### Task 3 — Collector config tuning

**File:** `examples/production/durable_postgres_otel/collector-config.yml` (edit)

Add explicit batch processor tuning + memory_limiter + resource processor:

```yaml
processors:
  batch:
    send_batch_size: 512
    timeout: 5s
  memory_limiter:
    check_interval: 1s
    limit_mib: 512
    spike_limit_mib: 128
  resource:
    attributes:
    - key: deployment.environment
      value: ${env:DEPLOYMENT_ENV}
      action: upsert
```

Document `DEPLOYMENT_ENV` env var in README.

### Task 4 — `docs/runbooks/otel-operations.md`

**File:** `docs/runbooks/otel-operations.md` (new)

Operator checklist file (per CLAUDE.md operator-actions rule). Sections:

1. **Provisioning checklist** (5 rows, each with action / owner / verification):
   - Replace Grafana admin default credential
   - Configure mTLS for OTel Collector → backend (prod only)
   - Set retention policy on Jaeger/Tempo for trace data (PHI residency)
   - Document chosen backend in SECURITY_MODEL.md §observability
   - Enable Prometheus AlertManager → PagerDuty / Slack webhook routing
2. **Runbook entries per alert** (4 sub-sections matching `alerts.yml`):
   - `DurableHighRoundLatency` triage
   - `DurableCipherDecryptFailureSpike` triage (includes "is a rotation in progress?" decision tree)
   - `DurablePauseResumeImbalance` triage
   - `DurableLockPoolNearSaturation` triage
3. **Cardinality budget** (refer to library D-OTEL-4 fixture test + how to add a new metric without breaking it)
4. **Container digest update procedure** (resolves the M-OTEL-SB-1 placeholder digests from Slice B audit)
5. **Backup/restore for Prometheus + Grafana state** (links to Tier 1.5 once shipped; today: documents the gap)

### Task 5 — Runbook flip: `durable-operations.md`

**File:** `docs/runbooks/durable-operations.md` (edit)

Flip rows from `REFERENCE-IMPL-PENDING` → `OPERATIONAL` in:
- SLO section: cite the alerts.yml file as the source of SLO definitions
- Log→alert mapping: link to `otel-operations.md` per-alert runbook entries
- Capacity sizing: cite the lock-pool saturation alert as the capacity signal

Add a forward-reference row pointing at `otel-operations.md` for OTel-specific operator concerns.

### Task 6 — Decision rows

**File:** `docs/decisions.md` (edit, append)

Add `D-OTEL-1..5` per spec §10. One row per decision; 2-3 sentences each. Cross-reference the spec file path.

### Task 7 — `SECURITY_MODEL.md` update

**File:** `docs/SECURITY_MODEL.md` (edit)

Add `§observability` subsection covering:
- The OTLP export trust boundary
- PII redaction posture (D-OTEL-2 allowlist)
- Tag-value cardinality discipline (D-OTEL-4 fixture test)
- Residual risks (metrics-tag PHI is unrecoverable post-export — primary defense is the test, not redaction)
- Operator-owned: backend choice + retention + mTLS

Add wrap/unwrap row to sensitive-op table if not already there (Slice B's audit covered span-attribute redaction; metrics-tag redaction is library-side discipline only).

### Task 8 — PHI grep gate integration test

**File:** `examples/production/durable_postgres_otel/tests/test_phi_grep_gate.py` (new)

Test approach: use `InMemorySpanExporter` from OTel SDK + run a synthetic workflow that intentionally tries to leak PHI through span attributes + exception messages. Wire `PIIRedactionSpanProcessor` in front of the in-memory exporter. After flush, dump all spans to JSON; grep the JSON for:

- `gAAAAA` (Fernet token prefix)
- `:5432/` (postgres DSN shape with password)
- Synthetic PHI markers: `SSN_FAKE_PATTERN`, `MRN_FAKE_PATTERN`, `PATIENT_FAKE_PATTERN`
- The literal string `password=` (catch any accidental DSN logging)

Assert grep returns ZERO hits. Failure means redaction has a hole.

Test file lives under the OTel sibling tests dir; excluded from library suite (per Slice B's `testpaths` gating).

### Task 9 — Cycle-11b security audit

Spawn an Agent (subagent_type=general-purpose) on:

> Security audit cycle-11b — closing audit on the full OTel deployment surface after Slice C operational dressing lands. Scope: `examples/production/durable_postgres_otel/` (full directory) + the 4 doc files this slice edits (`docs/runbooks/otel-operations.md`, `docs/runbooks/durable-operations.md` deltas, `docs/decisions.md` D-OTEL rows, `docs/SECURITY_MODEL.md` §observability). Inherits cycle-11a posture (0 CRIT / 0 HIGH / 3 MED / 2 LOW). Specific watch-items: (1) alert rule expressions — do any leak PHI through alert annotations? (2) Grafana dashboard JSON — any PHI-shaped query labels? (3) operator runbook — does it correctly document the placeholder-digest remediation from M-OTEL-SB-1? (4) D-OTEL-2 allowlist drift — has Slice C silently expanded the allowlist beyond the spec? (5) test_phi_grep_gate coverage gaps. Report CRIT/HIGH/MED/LOW with file:line + remediation. Under 500 words.

Audit report → `docs/security-audits/2026-05-18-otel-slice-c-sweep.md`. Drain CRIT + HIGH inline before commit.

### Task 10 — NEXT_SESSION.md refresh

**File:** `docs/NEXT_SESSION.md` (edit, prepend a new section)

Section title: `## 2026-05-18 — Tier 1.1 SHIPPED (3-slice arc)`

Content:
- Slices A/B/C summary with commit ranges
- Final test count (library 710 + OTel sibling 9)
- Cycle-11a + 11b audit posture
- Runbook flip: `durable-operations.md` SLO + alert sections now OPERATIONAL
- Next-recommended: Tier 1.2 (k8s manifests — k8s-OTel pattern proven by Slice B/C compose stack) or Tier 1.4 (schema migration) or Tier 1.9 (Full-Checkpoint AEAD)

### Task 11 — Verify + commit chain

Pre-PR gate (library only):
```
python scripts/check_no_secrets.py
python -m ruff check .
python -m mypy src
python -m pytest -q
```

Library test count: 710 (no change; OTel example tests excluded).

Commit chain (4-5 commits):
1. `feat(otel): Slice C - Grafana dashboard + Prometheus alerts + collector tuning`
2. `docs(otel): otel-operations.md runbook + durable-operations.md flip OPERATIONAL`
3. `docs(otel): D-OTEL-1..5 decision rows + SECURITY_MODEL observability section`
4. `test(otel): PHI grep gate integration test`
5. `docs: cycle-11b closing audit + NEXT_SESSION refresh [skip ci]`

Push after the chain.

---

## Sanity checks before declaring done

- [ ] Library `pyproject.toml` UNCHANGED across all 3 slices
- [ ] `python -m pytest -q` still reports 710
- [ ] Grafana dashboard JSON validates (`jq . dashboard.json` OK)
- [ ] `alerts.yml` PromQL expressions parse (manual review — no live promtool available)
- [ ] Operator-actions checklist file exists with ALL 5 rows
- [ ] `D-OTEL-1..5` rows present in `docs/decisions.md`
- [ ] Cycle-11b audit ran; 0 CRIT + 0 HIGH at final commit
- [ ] NEXT_SESSION refreshed with the 3-slice summary

## Out of scope (carry to Tier 1.2 or later)

- k8s manifest (Tier 1.2 lane)
- Production-grade collector with mTLS termination (operator-owned per otel-operations.md)
- Backend-specific dashboards (Tempo / Honeycomb / Datadog variants)
- Live trace recording smoke test (requires running collector; out of scope for unit-test layer)

## Commit-message hygiene reminder

PowerShell + bash choke on `&`, `>`, `<`, `|`, `&&` in `-m "..."`. Past burns logged in CLAUDE.md. Use words (`and`, `gt`, `lt`) or escape.
