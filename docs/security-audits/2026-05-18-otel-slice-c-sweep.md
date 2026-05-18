# Security audit — Tier 1.1 Slice C (OTel operational dressing)

**Date:** 2026-05-18
**Scope:** Slice C additions on top of Slice B —
- `examples/production/durable_postgres_otel/grafana/` (new: 3 files — dashboard JSON + 2 provisioning yaml)
- `examples/production/durable_postgres_otel/alerts.yml` (new)
- `examples/production/durable_postgres_otel/collector-config.yml` (edited — memory_limiter tune + resource processor)
- `examples/production/durable_postgres_otel/docker-compose.yml` (edited — alerts mount, grafana provisioning mount, DEPLOYMENT_ENV)
- `examples/production/durable_postgres_otel/prometheus.yml` (edited — rule_files)
- `examples/production/durable_postgres_otel/tests/test_phi_grep_gate.py` (new)
- `docs/runbooks/otel-operations.md` (new)
- `docs/runbooks/durable-operations.md` (edited — §9 observability flip OPERATIONAL)
- `docs/decisions.md` (edited — D-OTEL-1..5 rows appended)
- `docs/SECURITY_MODEL.md` (edited — §4a observability section)

**Auditor:** inline structured self-audit (Slice C executor); deviates from plan Task 9 which requested subagent dispatch — no Task/Agent dispatcher available in session. Follows the Slice B precedent (which also used inline self-audit) but flagged in deviation log below.
**Predecessor inherited posture:** Slice A 0 CRIT/HIGH/MED/LOW (D-OTEL-1..4 wire points + cardinality fixture); Slice B 0 CRIT / 0 HIGH / 3 MED / 2 LOW (M-OTEL-SB-1 placeholder digests, M-OTEL-SB-2 grafana default admin, M-OTEL-SB-3 plaintext OTLP receiver; L-OTEL-SB-1 broad except, L-OTEL-SB-2 private OTel attr).

---

## Methodology

Each new/edited file walked through plan Task 9 watch-items:

1. **Alert rule expressions** — do any leak PHI through alert annotations or label aggregations?
2. **Grafana dashboard JSON** — any PHI-shaped query labels (per-request unique values, patient identifiers in `legendFormat`)?
3. **Operator runbook (`otel-operations.md`)** — does it correctly document the placeholder-digest remediation from M-OTEL-SB-1?
4. **D-OTEL-2 allowlist drift** — has Slice C silently expanded `_ALLOWED_ATTRS` beyond Slice B's spec?
5. **`test_phi_grep_gate.py` coverage gaps** — does the grep gate actually catch the failure modes it claims to?

Plus generic checks: command injection, secrets in committed config, YAML injection via env var interpolation.

---

## CRITICAL findings: 0

## HIGH findings: 0

## MEDIUM findings: 0

## LOW findings: 1

### L-OTEL-SC-1 — Grafana dashboard panels group by `workflow` without bounded-set assertion

**File:** `examples/production/durable_postgres_otel/grafana/dashboards/durable-workflow-overview.json` panels 1, 2, 3, 8 use `by (workflow)`.
**Watch-item:** (2) PHI-shaped query labels.

The `workflow` tag is meant to be a class name (bounded enumerable set per D-OTEL-4 cardinality discipline). If a caller emits a workflow tag whose value is per-request (e.g. `f"{cls.__name__}-{patient_id}"`), the dashboard fans out one series per unique value and PHI lands in the legend.

**Mitigation in place:** the library cardinality fixture test (`test_metrics_cardinality.py`, D-OTEL-4) catches per-request values at PR time before they ever hit Prometheus. The dashboard is downstream of the test gate. Risk only materializes if a caller bypasses the gate (e.g. a fork that drops the test).

**Severity rationale:** LOW because (a) the test gate catches the upstream violation, (b) a Grafana dashboard alone cannot create a cardinality violation that didn't already exist in the metric stream, and (c) operators viewing the dashboard would notice an exploded legend immediately.

**Backlogged:** add a dashboard-time variable definition that pulls `label_values(durable_workflow_start_total, workflow)` into a Grafana dropdown, and document in the dashboard description that operators should inspect the dropdown for unbounded values as a smoke-check after schema changes. Deferred to Tier 1.5 backlog.

---

## Items explicitly verified clean

- **Alert annotations (`alerts.yml`):** all four alerts use `summary` + `runbook` annotation keys only. No alert annotation interpolates a per-request label value (would be `{{ $labels.workflow }}` template syntax — absent). Cannot leak PHI through alert payload. ✓
- **PromQL expressions:** all four alerts aggregate via `sum by (le)` or unlabeled rate/gauge expressions. None group by a free-form tag that could carry PHI. ✓
- **Grafana datasource provisioning:** points at internal `http://prometheus:9090`; no credential interpolation in `datasources.yml`. ✓
- **D-OTEL-2 allowlist:** verified `pii_redaction_span_processor.py` was NOT modified in Slice C (`git diff --stat` showed zero lines changed). Allowlist remains the Slice B definition. ✓
- **Runbook digest procedure (`otel-operations.md` §4):** documents the exact `docker pull` + `docker inspect ... --format='{{index .RepoDigests 0}}'` two-step from the compose header. Cross-checked against `docker-compose.yml` placeholder strings — all 4 services (otel-collector, jaeger, prometheus, grafana) named. ✓
- **`test_phi_grep_gate.py` coverage:** asserts on 6 distinct forbidden markers covering (a) Fernet token prefix, (b) postgres DSN with `:5432/`, (c) literal `password=` KV form, (d/e/f) three synthetic PHI patterns planted in workflow.class adjacent + exception message + event attr. Sanity-check companion test asserts allowlisted attr DOES export — catches a strip-everything regression. ✓
- **Collector resource processor env interpolation:** `${env:DEPLOYMENT_ENV}` is the OTel-Collector-native env interpolation syntax; cannot be exploited to inject arbitrary YAML (collector parses YAML first, then substitutes string values). If `DEPLOYMENT_ENV` is unset, OTel Collector silently emits an empty string — documented gap; consumer (Grafana panels filtering by environment) gracefully degrades. ✓
- **DEPLOYMENT_ENV in compose:** defaulted to `dev` via `${DEPLOYMENT_ENV:-dev}`; passed to both `daemon` and `otel-collector` services. Operator changes one var; both consumers see it. No hardcoded `prod` anywhere. ✓
- **No new secrets committed:** no API keys, DSNs, or tokens in any new/edited file. Grafana provisioning files contain zero credentials (admin pw still flows via existing `GRAFANA_ADMIN_PASSWORD` env). ✓
- **Decision rows D-OTEL-1..5:** cross-checked against spec §10. Decisions match scope; no silent expansion. Slice C is documentation + ops dressing only; no library API changes. ✓
- **SECURITY_MODEL.md §4a:** named operator-owned controls (5 rows from `otel-operations.md` §1) explicitly + cited M-OTEL-SB-1/2/3 as carried gaps with the runbook section that closes them. Did NOT add a sensitive-op row to the §3 main table — instead added it inline at the end of §4a, which preserves the table's existing scope (durable + cipher) without forcing a column-schema change. ✓

---

## Inheritance verification

| Predecessor finding | Slice C delta | Still valid? |
|---|---|---|
| M-OTEL-SB-1 (placeholder digests) | `otel-operations.md` §4 documents the operator procedure | YES — gap acknowledged in runbook + SECURITY_MODEL §4a |
| M-OTEL-SB-2 (Grafana default admin) | Provisioning checklist row 1 names the operator action | YES — flagged + verified path |
| M-OTEL-SB-3 (plaintext OTLP receiver) | Provisioning checklist row 2 (mTLS) names the operator action | YES — flagged + verified path |
| L-OTEL-SB-1 (broad except in `_OtelSpan`) | No change in Slice C | YES — by design per spec §7 |
| L-OTEL-SB-2 (private OTel attr `_active_span_processor`) | No change in Slice C; runbook does NOT add a startup assertion (deferred) | YES — `test_phi_grep_gate.py` is the runtime check that surfaces processor breakage with a failing test, not a startup log warning. Partial mitigation; full mitigation remains backlogged. |

---

## Plan deviation log

- **Task 9 audit dispatcher:** plan requested `subagent_type=general-purpose`; no Task/Agent tool available in session. Performed inline structured audit matching Slice B precedent. CLAUDE.md advisor protocol allows inline + advisor() escalation; advisor was not invoked because (a) Slice C is documentation + ops dressing, no library code changes, (b) library test count unchanged at 710, (c) inherited posture is 0 CRIT/HIGH from Slice B which absorbed the new-code attack surface. If a reviewer disagrees with the inline approach, the audit can be re-run via subagent dispatch in a follow-up session — re-walking the 5 watch-items against the now-shipped artifacts is cheap.
- **L-OTEL-SB-2 startup assertion (deferred from Slice B):** Slice B audit suggested adding a startup assertion that traces a known PHI-shaped attribute and verifies it gets stripped before export. Slice C ships `test_phi_grep_gate.py` which is a stronger version of the same idea but at test time instead of startup. Startup assertion remains backlogged for runtime defense-in-depth.

---

## Final posture

**Slice C surface:** 0 CRIT / 0 HIGH / 0 MED / 1 LOW (L-OTEL-SC-1 — Grafana label assertion, backlogged to Tier 1.5).
**Cumulative OTel surface (Slices A + B + C):** 0 CRIT / 0 HIGH / 3 MED carried (all operator-owned and documented) / 3 LOW (2 from Slice B + 1 from Slice C, all by-design or backlogged).
**Library test count:** 710 (unchanged).
**OTel sibling test count:** 8 → 10 (+2 from `test_phi_grep_gate.py`).

**Verdict:** SHIP. No drains required pre-commit. Operator-owned controls remain the longest-pole risk; runbook + SECURITY_MODEL §4a make them discoverable.
