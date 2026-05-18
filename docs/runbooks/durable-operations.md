# Durable Workflow — Operations Runbook

**Audience:** SRE / DevOps / Eng Manager owning production operation of `DurableWorkflow`-wrapped callers.
**Scope:** Structured log → alert mapping, SLOs, capacity sizing, failure-mode response matrix, on-call entry points, schema-version migration procedure.
**Status legend:** `SHIPPED` (library provides) · `OPERATOR-OWNED` (SRE configures) · `REFERENCE-IMPL-PENDING` (library backlog).

Cross-refs: `docs/runbooks/durable-integration.md` (engg IC) · `docs/runbooks/durable-compliance.md` (regulatory) · `docs/SECURITY_MODEL.md` (threat model) · `docs/security-audits/2026-05-16-durable-poc-sweep.md` (cycle 7 audit closure).

---

## 1. SLO targets (recommended baselines)

Tune to your domain. These are starting points calibrated against the healthcare ClinicalTrial reference deploy.

| SLO | Target | Window | Rationale |
|---|---|---|---|
| **Resume success rate** | ≥ 99.5% | 30-day rolling | A failed resume = paused human in the loop; degrades workflow's user-facing latency |
| **Checkpoint write success rate** | ≥ 99.9% | 30-day rolling | Failure = round work lost; caller retries on idempotent `run_id` |
| **Pause-to-wake latency overshoot** | ≤ 60s above `wake_at` p95 | 7-day rolling | Daemon poll cadence is 60s default; tighter only if SLA demands |
| **`ReconciliationHook` p95 latency** | ≤ 10s | 7-day rolling | Default timeout is 30s; p95 at 10s leaves headroom |
| **Budget breach surface time** | ≤ 5 min from breach to alert | per-incident | Catches runaway loops before USD damage compounds |
| **Stale lock reclaim** | ≤ TTL + 2 min | per-incident | Past TTL + `_MIN_TTL=1` overshoot; longer = wedge |
| **Schema migration completion** | ≤ 4 hours | per-migration | Bounded by total checkpoint count; see §8 |

---

## 2. Structured log fields → alert mapping

Each terminal state of a `DurableWorkflow` run writes one structured log line (SHIPPED). Field schema:

```
run_id, workflow_class, status, rounds_completed, duration_s,
tokens_in, tokens_out, usd_spent, pause_reason, pinned_executor_model,
pinned_reviewer_model, schema_version
```

**No PHI in logs** — matches healthcare workflow posture (D-HEALTH-3 + D-DURABLE-1).

**Alert matrix (configure in your aggregator):**

| Signal | Severity | Page or Ticket | Action |
|---|---|---|---|
| `status="budget_exceeded"` | HIGH | Page if > 1 in 10 min; otherwise ticket | Caller raised cap unintentionally OR runaway loop. Inspect `rounds_completed` — if N > MAX_REVIEW_ROUNDS, code bug |
| `status="failed"` + `error~="ModelRetired"` | HIGH | Page | Pinned model retired by provider. Triage: confirm with provider docs; decide `force_model_upgrade` policy |
| `status="failed"` + `error~="SchemaVersionMismatch"` | MEDIUM | Ticket | Caller deployed new lib version before migrating checkpoints. See §8 |
| `status="failed"` + `error~="RunLocked"` | LOW | Ticket if > 10/hour | Concurrent resume attempts. Normal during scheduler retry; suspicious if sustained |
| `status="failed"` + `error~="CheckpointCorrupt"` | HIGH | Page | Disk corruption or bug. Recover from backup; preserve corrupt file for post-mortem |
| `status="failed"` + `error~="ReconciliationFailed"` | MEDIUM | Ticket | Caller hook raised or timed out. Caller fix needed |
| `pause_reason="regulatory_clock"` + `wake_at - now > 7d` | INFO | Dashboard only | Visibility into pending regulatory windows |
| `SchedulerDaemon._quarantine.size > 0` | HIGH | Page | Tokens that failed `max_retries=3`. Manual intervention required (see §5) |
| `usd_spent / max_usd > 0.8` mid-run | MEDIUM | Ticket | Approaching budget cap; consider raising before next round |

**Suggested aggregator queries (Datadog / Splunk syntax sketches):**

```
# Hourly failure rate by status
| status:failed | timechart count by error_type span=1h

# Top workflows by budget burn
| sort -usd_spent | head 10

# Quarantined tokens
| metric:scheduler.quarantine_size | last(5m) > 0
```

---

## 3. Failure-mode response matrix

Inherits from design spec §5 + audit cycle 7 closures. Each row maps a runtime failure to the on-call action.

| # | Failure | Detection | Immediate action | Root-cause check |
|---|---|---|---|---|
| 1 | Checkpoint write fails mid-round | `OSError` in logs | None (caller idempotent retry) | Disk full · permissions · workspace mount lost |
| 2 | Checkpoint corrupt at resume | `CheckpointCorrupt` in logs | Move corrupt file aside; restore from backup if exists; else cancel run | Concurrent writer not using `RunLock` · partial write before atomic-rename · ENC corruption |
| 3 | Schema version mismatch | `SchemaVersionMismatch` in logs | Run migration tool (see §8); resume after | Caller deployed before migration · migration tool incomplete |
| 4 | Pinned model retired | `ModelRetired` in logs | Triage: confirm with provider; if accepted, resume with `force_model_upgrade=True` | Anthropic/OpenAI EOL’d the pinned model |
| 5 | Budget exceeded mid-call | `BudgetExceeded` in logs | Verify with caller; raise cap and resume, or cancel | Caller misjudged cost per round · prompt regression inflating tokens · runaway loop |
| 6 | Reconciliation hook raises | `ReconciliationFailed` in logs | Notify caller; checkpoint stays paused; caller fixes hook + retries | Hook bug · external API down · idempotency violation |
| 7 | Reconciliation hook times out | `asyncio.TimeoutError` wrapped | Same as #6; check downstream API SLO | External API slow · timeout misconfigured |
| 8 | Agent API timeout / network | Exception in logs | None (caller retries `resume(token)`) | Provider degraded · network partition · key rotation incident |
| 9 | Concurrent resume of same run_id | `RunLocked` in logs | None below threshold (10/hour); investigate if sustained | Scheduler retry storm · operator dual-trigger · stale lock not yet reclaimed |
| 10 | Stale lock past TTL | Lock file mtime + TTL elapsed | Reclaim automatic; manual if filesystem clock skewed | Process crashed without `release()` · clock skew |
| 11 | Daemon `_quarantine` populated | Metric + log line | See §5 (quarantine drain procedure) | Repeated reconciliation failure · model retire · DB unreachable |
| 12 | Resume of vetoed run | `RunHaltedByVeto` in logs | None — by design. Caller must `cancel()` and re-`start()` if appeal flow | Operator confused — re-read pause-vs-veto semantics |

---

## 4. Capacity sizing

**See [`docs/capacity-model.md`](../capacity-model.md) for the published cost + capacity table at 100 / 1K / 10K / 100K paused runs** (Tier 2.5 ship). The numbers below are the operational rules-of-thumb the model is built on; the published table is the source of truth for sizing decisions.

POC posture is single-process; production swaps the three Protocols. Numbers below are for the `PostgresCheckpointStore` reference target (REFERENCE-IMPL-PENDING).

### 4.1 Storage

| Component | Per-run cost | Math |
|---|---|---|
| Checkpoint row | ~5-20 KB | `last_request_json` (≤ N fields × 1500 chars) + `rounds_history` (~2 KB/round) |
| 100K paused runs | 500 MB - 2 GB | Linear in run count |
| Append-only audit (if separate) | ~10 KB/round | Multiply by expected total rounds across lifetime |

**Cleanup:** `CheckpointStore.delete(run_id)` is idempotent. Retention policy: see compliance runbook §6.

### 4.2 Compute (single `SchedulerDaemon`)

| Workload | Recommendation |
|---|---|
| Up to 1K paused runs | One daemon process, `poll_interval_seconds=60` |
| 1K - 10K | One daemon, tune `poll_interval_seconds=15` and add `batch_size` limit |
| 10K - 100K | Shard by `workflow_class`; one daemon per shard |
| 100K+ | Replace `PollingScheduler` with `TemporalScheduler` / `pg-boss` (REFERENCE-IMPL-PENDING) |

**Daemon CPU:** poll + N concurrent resumes. Bound concurrency via daemon-level `asyncio.Semaphore` (caller-implementable).

### 4.3 Agent API throughput

`BudgetTracker` is per-run. Org-wide rate-limiting is **CALLER-OWNED** — wrap your `ExecutorAgent` / `ReviewerAgent` with whatever rate-limit middleware your platform standardizes on.

Rule of thumb: 1 concurrent resume = ~2 agent API calls in flight (executor + reviewer). Plan provider rate-limit headroom accordingly.

---

## 5. Operational procedures

### 5.1 Stuck-paused-run remediation

A run sits in `status="paused"` past expected resume window. Decision tree:

1. **Read checkpoint via SQL or `CheckpointStore.read()`** — confirm `pause_reason`, `wake_at`, `rounds_history`.
2. **Check daemon liveness** — is `SchedulerDaemon` running? Last poll timestamp recent?
3. **Check quarantine** — has the daemon given up on this token? (`SchedulerDaemon._quarantine`)
4. **Check `RunLock`** — is the run actually locked by a stuck worker?
5. **Triage:**
   - If `wake_at` is None (explicit-resume), caller is expected to trigger — confirm with caller
   - If `wake_at` is past + daemon healthy + not quarantined, file library bug
   - If quarantined, see §5.2

**Force-resume** (operator override, OPERATOR-OWNED):

```python
# Use only when triage above complete and operator owns the consequence.
token = ResumeToken(...)  # rehydrate from checkpoint
outcome = await durable.resume(token, force_model_upgrade=False)
```

### 5.2 Quarantine drain procedure

`SchedulerDaemon` quarantines tokens after `max_retries=3` (SHIPPED — closure of L-DUR-4). Drain steps:

1. **List quarantined tokens** — `daemon._quarantine` is a `set[str]` of `run_id`s.
2. **For each `run_id`:** read checkpoint; identify the failure (look at last `rounds_history` entry's error field).
3. **Address root cause** — caller hook bug? provider outage resolved? key rotated?
4. **Manually call `resume(token)` once** to verify recovery.
5. **Clear from quarantine** — daemon restart drops the in-memory set (acceptable for POC; production scheduler impl should persist quarantine to checkpoint metadata).

**Anti-pattern:** clearing quarantine without fixing root cause. Will loop back into quarantine on next `max_retries` failures.

### 5.3 Stale lock cleanup

`FileRunLock` reclaims past TTL via mtime + persisted TTL (closure of M-DUR-2). If filesystem clock is skewed:

1. Verify NTP sync on the host.
2. If skew confirmed, manually delete `<run_id>.lock` file (operator action; logged).
3. Retry resume.

`PostgresAdvisoryLock` (REFERENCE-IMPL-PENDING) reclaim is automatic on session close — no manual cleanup needed.

### 5.4 Daemon restart procedure

`SchedulerDaemon` is stateless across restart (state lives in `CheckpointStore`). Procedure:

1. SIGTERM the existing daemon. Wait for graceful drain (in-flight resumes complete).
2. Start new daemon process pointing at same `CheckpointStore`.
3. Daemon resumes polling; previously-paused runs are picked up on next poll.
4. **Quarantine resets** — daemon's in-memory `_quarantine` is empty on start. Persist quarantine to checkpoint metadata in production impl.

### 5.5 Budget cap raise mid-run (Tier 2.3 / D-BUDGET-1)

A run in `status="budget_exceeded"` requires an explicit operator action — `resume(token)` alone will raise `RunNotResumable` because the status is non-paused. The fail-closed default is intentional: a silent retry against the same cap would just re-exceed.

1. **Inspect.** Read `rounds_history`, count rounds, inspect last round's claim count. Confirm legitimate (not runaway loop). If runaway: skip step 2 and `cancel(token, reason="runaway_detected")`.
2. **Construct a NEW `DurableWorkflow` with a higher-cap `BudgetTracker`.** The cap must exceed the row's accumulated `budget_used` — otherwise the next `record()` call trips `BudgetExceeded` again on the first round and the checkpoint flips back to `budget_exceeded`.
3. **Acknowledge.** `await dw.acknowledge_budget_exceeded(token)` — flips status `budget_exceeded` → `paused` and appends a `budget_cap_acknowledged` audit row to `rounds_history` with the budget snapshot at acknowledge time. Library does the flip + reseal in one `store.write()`, so the integrity_tag is recomputed against the new canonical bytes. Raw operator edits to the row would leave the integrity tag stale and the next read would raise `IntegrityViolation`.
4. **Resume.** `await dw.resume(token)`. Library reconciles budget on resume (closure of L-DUR-5 — double-billing prevented).

```python
# Recovery skeleton
dw_higher_cap = DurableWorkflow(
    inner=inner_workflow,
    config=config,
    checkpoint_store=store,
    budget=BudgetTracker(max_usd=200.0),  # was 50.0; check rounds_history first
)
await dw_higher_cap.acknowledge_budget_exceeded(token)
outcome = await dw_higher_cap.resume(token)
```

Audit log: every acknowledge is recorded in `rounds_history` as `{event: "budget_cap_acknowledged", at: <ts>, budget_used_at_ack: {...}}`. Compliance reviewers can reconstruct who raised the cap and when by joining this trail with the operator's deployment logs.

---

## 6. Process management (`SchedulerDaemon`)

POC ships `SchedulerDaemon.run_forever()`. Production:

### 6.1 systemd unit (sketch, OPERATOR-OWNED)

```ini
[Unit]
Description=adv-multi-agent durable scheduler daemon
After=network.target postgresql.service

[Service]
Type=simple
User=appuser
WorkingDirectory=/opt/myapp
EnvironmentFile=/etc/myapp/durable.env
ExecStart=/opt/myapp/.venv/bin/python -m myapp.durable_daemon
Restart=on-failure
RestartSec=10s
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
```

### 6.2 k8s Deployment (sketch, OPERATOR-OWNED)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: durable-scheduler
spec:
  replicas: 1  # single-process daemon; scale via SchedulerBackend impl swap
  strategy:
    type: Recreate  # do not run two daemons against same store without distributed lock
  template:
    spec:
      containers:
        - name: scheduler
          image: myapp:latest
          command: ["python", "-m", "myapp.durable_daemon"]
          envFrom:
            - secretRef:
                name: durable-env
          resources:
            requests:
              memory: 512Mi
              cpu: 250m
            limits:
              memory: 1Gi
              cpu: 1000m
          livenessProbe:
            exec:
              command: ["python", "-c", "import myapp.durable_daemon; myapp.durable_daemon.healthcheck()"]
            periodSeconds: 30
```

**Multi-replica caution:** `PollingScheduler` is NOT multi-replica safe — two daemons against same store will both try to resume the same paused token. `RunLock` prevents corruption but causes `RunLocked` log spam. Production multi-replica requires `PostgresAdvisoryLock` (REFERENCE-IMPL-PENDING).

---

## 7. Backup and restore

`CheckpointStore` is the only durable state the library owns. **OPERATOR-OWNED.**

| Impl | Backup approach |
|---|---|
| `FileCheckpointStore` | Snapshot the `base_dir`; tar + offsite. Cadence ≥ daily. Test restore monthly |
| `PostgresCheckpointStore` (OPERATIONAL — Tier 1.5) | See [`durable-backup-restore.md`](durable-backup-restore.md). `scripts/backup.sh` (encrypted pg_dump + manifest + cloud upload), `scripts/restore.sh` (fetch + decrypt + pg_restore + integrity sample), `postgresql.conf.snippet` (WAL archiving for PITR). RPO ≤ 1 WAL segment under PITR; RTO ≤ 2h. |
| `S3CheckpointStore` (REF-PENDING) | S3 versioning + cross-region replication |

**Restore verification:**

1. Restore to staging environment.
2. Run library tests against restored store: `pytest tests/unit/durable/test_checkpoint.py -q`.
3. Pick a sample `run_id`; deserialize and inspect via `CheckpointStore.read()`.
4. Verify `schema_version` matches running library version (else: trigger migration, §8).

**RPO/RTO targets:**

| | Recommendation | Tune to |
|---|---|---|
| RPO (data loss tolerance) | ≤ 1 hour | Cost of replaying lost rounds (USD per round × expected re-runs) |
| RTO (recovery time) | ≤ 4 hours | Caller's user-facing SLA on paused runs |

---

## 8. Schema-version migration procedure

`Checkpoint.schema_version` bumps when the dataclass shape changes incompatibly (D-DURABLE-1). **Status (post Tier 1.4, 2026-05-18):** mechanism + deployment script SHIPPED as `OPERATIONAL (scaffolding only)`. The library `REGISTRY` is **EMPTY at v1** by design — additive changes (Tier 1.6 `workflow_version_hash`, Tier 1.9 `integrity_tag`) ship without bumping the schema version via the nullable-field + deserializer-exemption convention documented in `core/durable/schema_migrations.py`. The first real migration lands the same day the first non-additive change does. Until then, running the tool against a healthy deployment is a verified no-op.

### 8.1 Procedure

1. **Freeze deploys.** No new library version rolls out during migration.
2. **Stop `SchedulerDaemon`** to prevent mid-migration resumes.
3. **Inventory** — `SELECT count(*), schema_version FROM checkpoints GROUP BY schema_version` (Postgres) or directory scan (File).
4. **Run migration tool** (dry-run first) — `python migrate_schema.py --dsn $DSN --dry-run` then `--apply`. Iterates checkpoints, applies registered migrations via `chain_migrations`, writes back with optimistic-CAS guard.
5. **Reseal** — `python reseal_all_checkpoints.py --dsn $DSN --apply`. Migration rewrites bytes; A10-H2 integrity tag must be recomputed. Skipping this step leaves every row failing tag verification on next read.
6. **Verify** — re-inventory; all rows at target version; sample read decrypts cleanly.
7. **Restart daemon.**
8. **Smoke-test** — resume one migrated token end-to-end.

### 8.2 Migration tool contract (OPERATIONAL — scaffolding)

- **Library:** `adv_multi_agent.core.durable.schema_migrations` — `REGISTRY: dict[int, Callable[[dict], dict]]` keyed by source version, `chain_migrations(row, target_version)` primitive, `MissingMigrationError` + `BrokenMigrationError` exceptions.
- **Deployment script:** `examples/production/durable_postgres/scripts/migrate_schema.py` — `--dry-run` default (D-SCHEMA-4), `--apply` explicit, forward-only (aborts on `schema_version > CURRENT_SCHEMA_VERSION` per D-SCHEMA-5), exit-code-0 clean / 1 CAS-conflicts / 2 abort.
- **Smoke tests:** `examples/production/durable_postgres/scripts/test_migrate_schema_smoke.py` — 4 tests exercising helper mechanism (no DB required).
- **Library mechanism tests:** `tests/unit/durable/test_schema_migrations.py` — 5 tests (empty registry no-op, synthetic v1->v2, missing migration error, broken migration error, chained v1->v3).

**Critical invariant:** the library runtime stays fail-closed (`Checkpoint.from_dict` raises on version mismatch). The migration tool is the ONLY supported bypass. It runs OFFLINE with the daemon stopped.

### 8.3 Rollback

Migrations are forward-only. To roll back:

1. Restore `CheckpointStore` from pre-migration backup (§7).
2. Deploy the pre-migration library version.
3. Resume daemon.

**Do not** attempt to write a reverse transform unless the schema change is genuinely reversible (rare).

---

## 9. Observability (`MetricsBackend` Protocol)

**Status (post Tier 1.1, 2026-05-18):** `MetricsBackend` Protocol SHIPPED in library (Slice A, commit `52388a4`). OTel sibling SHIPPED with `OtelMetricsBackend` + PII redaction span processor (Slice B, commits `4f97968`..`9b8a669`). Grafana dashboard + Prometheus alert rules + operator runbook SHIPPED (Slice C, 2026-05-18). Library still emits structured log lines unchanged for callers who choose `_NoopMetricsBackend` (default).

| Signal | Library source | OTel sibling surface |
|---|---|---|
| Counters (runs started / completed / failed by status, pauses by reason) | `MetricsBackend.counter` | Prometheus metric `durable_workflow_*_total`; Grafana panels 1 + 2 |
| Latencies (p50/p95/p99 round duration, lock-acquire latency) | `MetricsBackend.histogram` | Prometheus `durable_round_latency_seconds_bucket` + `durable_lock_acquire_latency_seconds_bucket`; Grafana panels 3 + 5 |
| Gauges (lock pool saturation, budget tokens, schema_version distribution) | `MetricsBackend.gauge` | Prometheus `durable_lock_pool_saturation` + `durable_budget_*`; Grafana panels 6 + 8 |
| Cipher decrypt failure rate | `MetricsBackend.counter` (Slice A) | Prometheus `durable_cipher_decrypt_failed_total`; Grafana panel 7; alert `DurableCipherDecryptFailureSpike` |
| Round-level traces (per-round async ctx mgr) | `MetricsBackend.span` | Jaeger via OTel Collector |

**SLO surface (§1 above) now OPERATIONAL via:** `examples/production/durable_postgres_otel/alerts.yml` defines the four default alerts wired to the runbook entries in `docs/runbooks/otel-operations.md` section 2. Capacity sizing (§4) is observable via the `durable_lock_pool_saturation` gauge — the `DurableLockPoolNearSaturation` alert is the capacity signal.

**Log-to-alert mapping (§2 above)** remains the source of truth for log-driven alerting; metric-driven alerting is additive and runs alongside.

**For OTel-specific operator concerns** (Grafana provisioning, alert wiring, container digest refresh, PII boundary for span attributes, cardinality budget, mTLS for the collector receiver): see `docs/runbooks/otel-operations.md`.

---

## 10. On-call entry points

| Symptom reported | Start here |
|---|---|
| "Runs stuck" / "paused forever" | §5.1 — stuck-paused-run remediation |
| "Daemon not picking up runs" | §5.4 — daemon restart, then §5.2 if quarantine populated |
| "USD spend spike" | §3 row 5; verify with caller; §5.5 cap raise procedure |
| "Resume failed with ModelRetired" | §3 row 4; triage `force_model_upgrade` policy with caller |
| "Resume failed with SchemaVersionMismatch" | §8 — migration procedure |
| "Lock errors in logs" | §3 row 9; if sustained, §5.3 stale lock cleanup |
| "Daemon process keeps crashing" | Check systemd/k8s logs; verify `CheckpointStore` reachable; verify env (api keys, cipher key) |
| "Checkpoint disk filling" | Retention policy (compliance runbook §6); §7 backup-and-trim |

---

## 11. Health checks

**Daemon liveness (operator-implementable):**

```python
async def healthcheck() -> dict:
    return {
        "daemon_running": True,
        "last_poll_at": daemon._last_poll_ts,  # private but readable
        "paused_runs": await store.count_by_status("paused"),
        "quarantine_size": len(daemon._quarantine),
        "checkpoint_store_reachable": await store.ping() if hasattr(store, "ping") else "n/a",
    }
```

**Aggregator alerts on healthcheck:**

| Signal | Threshold | Severity |
|---|---|---|
| `daemon_running == False` | any | PAGE |
| `now - last_poll_at > 2 * poll_interval` | sustained 5 min | PAGE |
| `quarantine_size > 0` | sustained 10 min | TICKET |
| `paused_runs` growth rate | > 2σ above baseline | TICKET |

---

## 12. Coordination with caller (engg IC)

The runbook split is intentional — many failures require eng + ops collaboration. Boundary lines:

| Failure | SRE owns | Engg IC owns |
|---|---|---|
| Disk full / DB unreachable | Yes | — |
| Reconciliation hook bug | Triage | Fix |
| Workflow logic bug | Triage | Fix |
| Budget cap misconfiguration | Detect | Set new cap |
| Model retire response policy | Operational reaction | Long-term policy |
| Schema migration tool | Run | Author |
| New `*Store` / `*Lock` impl | Deploy | Author + contract-test |

Use `docs/runbooks/durable-integration.md` §10 graduation checklist as the joint sign-off artifact.

---

## 13. GCP KMS key rotation (GcpKmsCipher deployments only)

Applies when `CIPHER_BACKEND=gcp_kms`. `FernetCipher` deployments use the procedure in
`docs/runbooks/durable-compliance.md` §5.2.

### 13.1 Rotation procedure

No daemon restart required. KMS version ID is embedded in the wrapped DEK; the KMS service routes
decrypt calls to the correct version automatically.

```bash
# Step 1: create a new primary key version
bash examples/production/cipher_gcp_kms/scripts/rotate_kms_key_version.sh \
  YOUR_PROJECT us-central1 durable-checkpoints payload-dek-wrapper

# Step 2: verify new version is primary
gcloud kms keys versions list \
  --keyring=durable-checkpoints --location=us-central1 \
  --key=payload-dek-wrapper --project=YOUR_PROJECT \
  --format="table(name, state)"
# Expect exactly one ENABLED version marked as primary.

# Step 3: no daemon restart needed — new encrypts use new primary; old ciphertext still decrypts.

# Step 4: log the rotation event in your change management system.
```

Prior key versions remain ENABLED so that existing wrapped DEKs can still be decrypted. Disable old
versions only after confirming all in-flight paused runs have resumed and completed (i.e., no
checkpoint holds a wrapped DEK from the old version).

**Frequency:** quarterly at minimum per HITRUST CSF KSP.02.05; immediately on suspected daemon SA compromise.

### 13.2 KMS-specific alert thresholds

Wire these to your log aggregator / Cloud Monitoring workspace. The `dek_cache_hit_count` and
`dek_cache_miss_count` metrics are emitted by `GcpKmsCipher` when wired to a `MetricsBackend`
(REFERENCE-IMPL-PENDING; structured logs are the interim surface).

| Signal | Threshold | Severity | Action |
|---|---|---|---|
| `dek_cache_miss_rate > 50%` sustained 10 min | HIGH | Ticket | Cache may be thrashing (TTL too short, max_size too small) or process is restarting frequently. Check `DEK_CACHE_TTL_SECONDS` and `DEK_CACHE_SIZE`. |
| KMS Decrypt p99 latency > 200 ms | MEDIUM | Ticket | Network path to KMS is degraded or KMS quota is being approached. Check Cloud Console KMS metrics. |
| KMS Decrypt error rate > 0.1% sustained 5 min | HIGH | Page | Possible SA permission revocation, key version destroyed, or KMS API quota exceeded. Check Cloud Audit Logs. |
| Cloud Audit Log gap > 15 min for `cloudkms_cryptokey` resource | HIGH | Page | Audit log export pipeline is broken. Compliance gap if log continuity is required. |
| `status="failed"` + `error~="KmsDecryptError"` in daemon log | HIGH | Page | Daemon SA cannot decrypt. Verify IAM grants (`scripts/audit_iam_grants.sh`) and key version state. |

### 13.3 IAM grant audit (pre-deploy gate)

Run before every deploy that touches IAM or the compose file:

```bash
bash examples/production/cipher_gcp_kms/scripts/audit_iam_grants.sh \
  YOUR_PROJECT us-central1 durable-checkpoints payload-dek-wrapper
```

Expected output: exactly two principals listed — daemon SA with `cryptoKeyEncrypterDecrypter`,
admin SA with `cloudkms.admin`. Any additional principal is a finding.

---

## §14 Alert: WORKFLOW_VERSION_DRIFT

Trigger: any paused run with `pause_reason=WORKFLOW_VERSION_DRIFT`.

Severity: P2. One drift is an operator-action gate — it means a code deploy
landed while a run was paused, and the operator must consciously roll back
or accept the drift.

Page after 0 hits (immediate alert). Page contains the run_id, checkpoint
hash, current hash, and link to compliance runbook §12.
