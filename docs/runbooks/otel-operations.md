# Runbook — OTel sibling deployment operations

**Scope:** `examples/production/durable_postgres_otel/` — OTel Collector + Jaeger + Prometheus + Grafana stack layered on top of `durable_postgres`.
**Source spec:** `docs/superpowers/specs/2026-05-18-otel-deployment-design.md`
**Library SLOs + log-mapping table:** `docs/runbooks/durable-operations.md` (this runbook references it but does not duplicate it).
**Status legend:** `SHIPPED` (sibling stack provides) · `OPERATOR-OWNED` (SRE configures before non-local deploy).

---

## 1. Provisioning checklist (pre-first-deploy)

Run top-to-bottom before any non-local deploy. Verification column names the command that confirms the step landed.

| # | Action | Owner | Verification |
|---|---|---|---|
| 1 | Replace Grafana admin default credential | SRE | Set `GRAFANA_ADMIN_PASSWORD` in `.env`; restart grafana; `curl -u admin:<new> http://127.0.0.1:3000/api/org` returns 200 |
| 2 | Configure mTLS for OTel Collector receiver and exporter (production only) | SRE | `collector-config.yml` `receivers.otlp.protocols.grpc.tls` populated with cert paths; collector log shows `TLS enabled`; daemon `OTEL_EXPORTER_OTLP_CERTIFICATE` set |
| 3 | Set retention policy on Jaeger / Tempo (PHI residency window) | SRE | Backend admin shows retention bounded to your data-residency policy (default Jaeger in-memory loses data on restart; production swap to badger/elasticsearch with bounded TTL) |
| 4 | Document chosen backend in `docs/SECURITY_MODEL.md` section observability | Eng IC | One row added naming backend + retention + region + IAM scope |
| 5 | Enable Prometheus AlertManager and wire to PagerDuty / Slack | SRE | `alertmanager.yml` provisioned; test alert fires through to on-call channel; runbook URLs in `alerts.yml` resolve |

**Additional pre-deploy:** resolve the placeholder digests from M-OTEL-SB-1 (see section 4 below).

---

## 2. Per-alert runbook entries

Each subsection matches an alert in `examples/production/durable_postgres_otel/alerts.yml`.

### 2.1 DurableHighRoundLatency

**Trigger:** `histogram_quantile(0.95, rate(durable_round_latency_seconds_bucket[5m])) > 30` for 10m.
**Severity:** warning.
**Hypothesis tree:**
1. Provider-side latency regression — check Anthropic / OpenAI status page; correlate against `model_fingerprint` tag on round spans.
2. Workflow regression — bisect against last deploy; if a prompt template grew, token counts grew, round latency grows linearly.
3. Reviewer model fan-out — verify reviewer hasn't been silently switched to a higher-latency model via env override.
4. Network egress saturation — daemon-to-provider RTT spike; check egress NIC utilization.

**Triage:** open the round-latency panel in `durable-workflow-overview.json`; group by workflow to isolate. If one workflow dominates, inspect its `rounds_history` for retry storms.

**Auto-remediation:** none. Manual triage required.

### 2.2 DurableCipherDecryptFailureSpike

**Trigger:** `rate(durable_cipher_decrypt_failed_total[5m]) > 0.1` for 5m.
**Severity:** critical.

**Decision tree:**
1. **Is a key rotation in progress?** If yes, the spike is expected for the rotation window. Confirm by cross-referencing `docs/runbooks/durable-operations.md` section 13 (GCP KMS rotation) — the operator on rotation duty should have an open change ticket. Acknowledge the alert with the ticket id; auto-resolve when rate returns to baseline.
2. **No rotation in progress?** Treat as potential key compromise OR backend outage. Page the cipher-on-call. Check the `cipher_backend` and `error_class` tags on the cipher decrypt failure panel:
   - `error_class=PermissionDenied` on GCP KMS → IAM policy regression; check `scripts/audit_iam_grants.sh` output diff
   - `error_class=NotFound` → key version disabled or destroyed unexpectedly; check Cloud KMS audit log
   - `error_class=InvalidCiphertext` → tampering OR cross-key contamination; quarantine the affected `run_id` and preserve checkpoint for forensics
   - `error_class=ServiceUnavailable` → KMS regional outage; rate-limit retries, watch the upstream status page
3. **Fernet backend?** A spike here almost always means key rotation or container env reload. Same triage path as KMS without the IAM step.

**Recovery:** if a single `run_id` is failing, mark it quarantined via `SchedulerDaemon._quarantine` semantics (see `durable-operations.md` section 5.2). If many `run_id` are failing, halt scheduler resume cycles until root cause is understood (sigterm the daemon; checkpoints remain durable; resume after fix).

### 2.3 DurablePauseResumeImbalance

**Trigger:** `(rate(durable_workflow_pause_total[1h]) - rate(durable_workflow_start_total[1h])) > 0` for 30m.
**Severity:** warning.

**Hypothesis tree:**
1. **Scheduler health** — is the daemon up? `docker compose ps daemon` shows `running (healthy)`? If unhealthy, see `durable-operations.md` section 5.4 restart procedure.
2. **Approver SLA** — paused runs awaiting human approval are stacking up faster than they're being resolved. Check the approver dashboard; if backlog is real, escalate to the approver pool.
3. **Reconciliation hook failures** — `status="failed"` + `error~="ReconciliationFailed"` log entries trending up; paused runs resume but immediately re-fail. Caller fix needed.
4. **Workflow-version drift block** — `pause_reason="workflow_version_drift"` accumulating. Operator must decide force-accept policy (see `durable-operations.md` section 14).

**Triage:** group the pause panel by `pause_reason` to isolate which reason dominates the imbalance.

### 2.4 DurableLockPoolNearSaturation

**Trigger:** `durable_lock_pool_saturation > 0.85` for 5m.
**Severity:** warning.

**Hypothesis tree:**
1. **Stuck runs** — locks acquired but never released. Check `durable-operations.md` section 5.3 stale lock cleanup; in Postgres advisory-lock mode reclaim is automatic on session close, so this almost always means a daemon hang.
2. **Capacity exhaustion** — legitimate concurrent run count exceeds POC sizing. Scale daemon replicas (see `durable-operations.md` section 6.2) OR raise the pool ceiling.
3. **Lock-acquire-failed counter trending up in parallel?** Then this is genuine contention, not stuck runs. Saturation is the leading indicator; failed acquisitions are the trailing indicator.

**Triage:** inspect the lock-pool saturation gauge alongside the lock-acquire-failed panel. Sustained 0.85+ saturation without failed acquisitions = headroom is shrinking but workload is being served; sustained 0.85+ saturation with rising failures = wedge.

---

## 3. Cardinality budget

The library enforces a tag-value cardinality budget via fixture test (D-OTEL-4 in `tests/unit/durable/test_metrics_cardinality.py`). Allowlisted tag keys live in `pii_redaction_span_processor.py` `_ALLOWED_ATTRS`.

**Adding a new metric:**
1. Add the metric in library `core/durable/metrics.py` with only allowlisted tag keys.
2. Run the cardinality fixture test; new tag keys without an allowlist entry will fail the test.
3. If the new key is genuinely safe (no PHI, no per-request unique values), add it to `_ALLOWED_ATTRS` in the sibling and to the fixture's allowlist. Both changes land in the same PR.
4. Spec the new metric in a D-OTEL-N row in `docs/decisions.md`.

**Smell test for "is this tag key safe":** "would I be comfortable seeing every distinct value of this tag in a Grafana dropdown indefinitely?" If the answer involves "well, the values are bounded because..." with a long sentence, the tag is unsafe. Truly safe tags have small enumerable domains (workflow class names, error classes, phase names).

---

## 4. Container digest update procedure

**Background:** Slice B audit M-OTEL-SB-1 — four images (`otel-collector`, `jaeger`, `prometheus`, `grafana`) ship with placeholder SHA-256 digests. Compose fails closed (image pull rejects placeholder) so first deploy surfaces the issue loudly.

**Procedure:**

1. Pull each image at its tag:
   ```
   docker pull otel/opentelemetry-collector-contrib:0.105.0
   docker pull jaegertracing/all-in-one:1.59.0
   docker pull prom/prometheus:v2.54.0
   docker pull grafana/grafana:11.1.0
   ```
2. Inspect each for the real digest:
   ```
   docker inspect otel/opentelemetry-collector-contrib:0.105.0 --format='{{index .RepoDigests 0}}'
   ```
3. Replace the four placeholder `@sha256:...` strings in `docker-compose.yml` with the real digests. Commit the change; reviewers can cross-check digests against the public registry.
4. Refresh quarterly OR on CVE alert for any of the four upstream images. Track refresh date in commit message body.

**Why digest-pinned and not tag-pinned:** tag-pinning permits a silent registry-side image swap; digest-pinning is content-addressed. This trades immediate convenience for supply-chain integrity.

---

## 5. Backup and restore for Prometheus and Grafana state

**Current posture:** documented gap. Tier 1.5 (backup/restore lane) will ship the procedure.

**Prometheus:** `/prometheus` volume holds the TSDB. `--storage.tsdb.retention.time=7d` bounds the window. Backups should snapshot the volume before any retention boundary; restore by mounting the snapshot into a new prometheus container.

**Grafana:** `/var/lib/grafana` holds dashboards (re-provisioned from JSON anyway), users, datasources (re-provisioned from yaml), alerts (snapshots only — alert RULE definitions live in `alerts.yml` and survive container loss). Backups are low-value if provisioning files are version-controlled, which they are in this stack. Restore is a fresh `docker compose up`.

**Action when Tier 1.5 ships:** replace this section with the productionized backup script + RTO/RPO targets.

---

## 6. Cross-references

- Library SLO definitions + log-to-alert mapping: `docs/runbooks/durable-operations.md` sections 1 + 2
- Failure-mode response matrix: `docs/runbooks/durable-operations.md` section 3
- GCP KMS rotation procedure (referenced by alert 2.2): `docs/runbooks/durable-operations.md` section 13
- Sibling stack threat model + PII boundary: `examples/production/durable_postgres_otel/README.md`
- Slice B closing audit: `docs/security-audits/2026-05-18-otel-slice-b-sweep.md`
- Slice C closing audit: `docs/security-audits/2026-05-18-otel-slice-c-sweep.md`
- Decision rows: `docs/decisions.md` D-OTEL-1..5
