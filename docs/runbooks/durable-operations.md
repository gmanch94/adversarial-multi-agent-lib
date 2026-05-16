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

### 5.5 Budget cap raise mid-run

A run in `status="budget_exceeded"`:

1. Confirm legitimate (not runaway loop) — read `rounds_history`, count rounds, inspect last round's claim count.
2. Update `BudgetTracker` instance with new cap.
3. Call `resume(token)`. Library reconciles budget on resume (closure of L-DUR-5 — double-billing prevented).

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
| `PostgresCheckpointStore` (REF-PENDING) | Standard Postgres backup — pg_dump or PITR. Treat the table as source of truth |
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

`Checkpoint.schema_version` bumps when the dataclass shape changes incompatibly (D-DURABLE-1). Migration tool is **REFERENCE-IMPL-PENDING** — sketch only.

### 8.1 Procedure

1. **Freeze deploys.** No new library version rolls out during migration.
2. **Stop `SchedulerDaemon`** to prevent mid-migration resumes.
3. **Inventory** — `SELECT count(*), schema_version FROM checkpoints GROUP BY schema_version` (Postgres) or directory scan (File).
4. **Run migration tool** — iterates checkpoints, applies transform, writes back. Idempotent on `(run_id, target_version)`.
5. **Verify** — re-inventory; all rows at target version.
6. **Restart daemon.**
7. **Smoke-test** — resume one migrated token end-to-end.

### 8.2 Migration tool contract (REFERENCE-IMPL-PENDING)

```python
class CheckpointMigrator:
    """Iterate all checkpoints; apply per-version transform."""

    transforms: dict[tuple[int, int], Callable[[dict], dict]]
    # key: (from_version, to_version); value: transform function

    async def migrate(
        self,
        store: CheckpointStore,
        target_version: int,
        dry_run: bool = True,
    ) -> MigrationReport: ...
```

### 8.3 Rollback

Migrations are forward-only. To roll back:

1. Restore `CheckpointStore` from pre-migration backup (§7).
2. Deploy the pre-migration library version.
3. Resume daemon.

**Do not** attempt to write a reverse transform unless the schema change is genuinely reversible (rare).

---

## 9. Observability gaps (`MetricsBackend` Protocol)

POC ships structured log lines only. `MetricsBackend` Protocol is a **named future seam** (REFERENCE-IMPL-PENDING) — design doc §7. Until then:

| Signal | Interim source |
|---|---|
| Counters (runs started / completed / failed by status) | Aggregator log queries (§2) |
| Latencies (p50/p95 round duration, hook duration) | Aggregator from `duration_s` field |
| Gauges (paused runs by reason, quarantine size) | `CheckpointStore.list_paused()` queried by daemon, exposed via daemon healthcheck endpoint |
| Budget (USD burn rate, token throughput) | Sum `usd_spent` over time window in aggregator |

**Production should plug** OTel / Prometheus / Datadog via a future `MetricsBackend` impl when the Protocol ships. Until then, every metric is derivable from log fields.

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
