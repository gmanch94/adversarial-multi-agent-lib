# Quarantine / dead-letter handling — design (Tier 2.4, advisor-revised cut)

**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Driver:** `docs/production-readiness-gaps.md` §2.4
**Advisor revision posture:** mirrors Tier 2.3 LEAN pattern — probe first, prefer surfacing existing convention over building a new abstraction. Result: quarantine today is **in-memory only on the daemon process**. The gap is therefore a *fuller build* than Tier 2.3 (status flip + persistence + operator surface), but smaller than a net-new dead-letter store. Recommend a **2-slice arc**: (S1) persist quarantine as a checkpoint status + library methods + scheduler skips persisted status; (S2) operator scripts + alert rule + runbook. Slices are independently shippable; S1 closes the durability gap, S2 closes the operator-workflow gap.

---

## 1. Current-state probe finding

Concrete evidence from grep across `src/`, `examples/`, `docs/runbooks/`:

| Surface | What exists today |
|---|---|
| `core/durable/scheduler.py:57–101` | `self._quarantine: set[str] = set()` — **in-memory** on `PollingDaemon` instance. Token added after `max_retries` (default 3) consecutive `RunNotFound` / `CheckpointCorrupt` / `SchemaVersionMismatch` / generic-Exception failures. Skipped on subsequent poll iterations. **Lost on daemon restart.** |
| `examples/production/durable_postgres/daemon.py:356`, `cipher_gcp_kms/daemon.py:429`, `durable_postgres_otel/daemon.py:142` | Healthcheck exposes `quarantine_size = len(daemon._quarantine)`. Counter only — no list, no inspect, no reason. |
| `core/durable/checkpoint.py:18` | `_STATUS_VALUES = {"running", "paused", "completed", "vetoed", "budget_exceeded", "failed"}`. **No `"quarantined"` value.** A crashing run lands `status="failed"` (or stays at last persisted status if the failure was pre-write) and the daemon-side set tracks the skip behavior. |
| No script under `examples/production/durable_postgres/scripts/` | No `list_quarantined.py` / `requeue_run.py` / `quarantine_delete.py`. |
| `examples/production/durable_postgres_otel/alerts.yml` | No quarantine-size or quarantine-growth rule. |
| `docs/runbooks/durable-operations.md` | Mentions quarantine concept; no operator-recovery flow. |

**Net.** "Quarantined" today means a `run_id` that the running daemon process happens to remember as having failed ≥3 times in its current process lifetime. It is not a persisted status, not visible across daemon restarts, not visible to other daemon instances, and not separable from `status="failed"` (which can also mean inner-workflow logic failure not retry-loop).

This is the **discriminating finding**: quarantine is *unimplemented* in the durable sense — only the *scheduler optimization* exists. The new lane is therefore a proper build (status value + persistence + library API + scheduler integration + operator scripts), not pure operational dressing.

---

## 2. Goal

Operator workflow for: (a) list quarantined runs (paginated, PII-redacted), (b) inspect why (audit trail in `rounds_history`), (c) re-queue after root-cause-fixed, (d) hard-delete, (e) alert on quarantine-size-growing.

**Library impact:** add `"quarantined"` to `_STATUS_VALUES`; add three public async methods to `DurableWorkflow` (`quarantine`, `requeue`, `list_quarantined`); change `PollingDaemon` to consult persisted status instead of (or in addition to) the in-memory set. No Protocol changes — uses existing `CheckpointStore` surface (`read` / `write` / `list_paused` extension or new `list_by_status`).

---

## 3. Locked design choices

### D-QUARANTINE-1: `"quarantined"` is a new status value, NOT a separate column

Add `"quarantined"` to `_STATUS_VALUES` in `checkpoint.py:18`. Rationale:

- Reuses the integrity_tag seal (Tier 1.9) — same atomic write path as `budget_exceeded` (Tier 2.3 precedent).
- Reuses every existing scheduler / store / store-encryption code path.
- Single source of truth for run state; querying becomes `list_by_status("quarantined")`.
- Avoids schema migration for a new column (Tier 2.6 cost) — only the status-set CHECK is touched.

Reject: separate `quarantined_at` / `quarantine_reason` columns. Reason: lives in `rounds_history` audit row instead (D-QUARANTINE-3).

### D-QUARANTINE-2: `DurableWorkflow.quarantine(token, reason)` signature

```python
async def quarantine(self, token: ResumeToken, reason: str) -> None: ...
```

Contract:
1. Reads checkpoint. Raises `RuntimeError` if `status in {"completed", "vetoed", "quarantined"}` (terminal or already quarantined — caller bug).
2. Sets `status = "quarantined"`.
3. Appends `{"event": "quarantined", "at": <ts>, "reason": <reason>, "failure_count_at_quarantine": <int from scheduler-supplied context or 0>, "previous_status": <prior>}` to `rounds_history`.
4. Single `store.write(cp)` — reseal + persist atomically.

`reason` is a free-form short string (operator- or scheduler-supplied). Recommended values: `"scheduler:max_retries"`, `"operator:bad_input"`, `"audit:phi_leak_suspected"`. No enum enforced — reasons evolve faster than library releases.

**Scheduler integration:** `PollingDaemon` upon reaching `max_retries` for a token calls `dw.quarantine(token, reason="scheduler:max_retries")` BEFORE adding to in-memory set. In-memory set remains as a fast-path skip; persisted status is the source of truth across restarts.

### D-QUARANTINE-3: `DurableWorkflow.requeue(token)` signature + idempotency

```python
async def requeue(self, token: ResumeToken) -> None: ...
```

Contract:
1. Reads checkpoint. Raises `RuntimeError` if `status != "quarantined"`.
2. Reads `requeue_count` from the latest `quarantined` event in `rounds_history` (0 if first requeue). **Fail-closed at 3:** raise `RuntimeError("requeue limit exceeded; investigate root cause or delete")` if count ≥ 3.
3. Sets `status = "paused"` (returns run to the normal resumable lane, NOT to its prior status — `paused` is the universal entry point).
4. Appends `{"event": "requeued", "at": <ts>, "requeue_count": <prior+1>, "by": "operator"}` to `rounds_history`.
5. Single `store.write(cp)` — reseal + persist atomically.

**Idempotency:** explicitly NOT idempotent. Second call on same checkpoint raises (status is now `paused`, not `quarantined`). Surface unexpected state per Tier 2.3 precedent.

**Loop detection:** scheduler increments `requeue_count` in the next `quarantined` event when re-quarantining. Three requeues + three failures → hard stop; operator must `cancel(token, reason="poisoned")` or `quarantine_delete` (D-QUARANTINE-6).

### D-QUARANTINE-4: `DurableWorkflow.list_quarantined(limit, offset)` returns PII-redacted summaries

```python
async def list_quarantined(
    self, *, limit: int = 50, offset: int = 0
) -> list[QuarantineSummary]: ...
```

`QuarantineSummary` is a new frozen dataclass exposing **only allowlisted columns**:

```
run_id: str
schema_version: int
quarantined_at: str          # extracted from latest "quarantined" event
reason: str                   # ditto
requeue_count: int            # ditto
previous_status: str          # ditto
workflow_class: str           # from token / pinned_executor_model proxy
pinned_executor_model: str
pinned_reviewer_model: str
created_at: str
updated_at: str
```

**Excluded (PII / sensitive):** `last_request_json`, `pause_context`, `rounds_history` body, `budget_used` line items, `integrity_tag`. Per Tier 1.1 PII discipline + the alert-rule template's allowlist precedent.

Operators wanting the audit trail call `read_checkpoint(token)` (existing surface) on a specific `run_id` — that path is already governed by the deployment's auth model + audit logging. `list_quarantined` is the *low-trust monitoring surface*; deep inspection is *higher-trust*.

Pagination is offset-based (matches existing `list_paused`); no cursor needed at POC scale (<10k quarantined rows).

### D-QUARANTINE-5: `resume()` refuses `status="quarantined"`

`DurableWorkflow.resume(token)` already raises `RunNotResumable` for non-`paused` status. Confirm `quarantined` falls into this rejection (it will, since the check is whitelist `status == "paused"`). Add one regression test.

Operator MUST call `requeue` first; cannot skip past the audit row + count check.

### D-QUARANTINE-6: Three operator scripts — pattern mirrors `reseal_all_checkpoints.py`

All three under `examples/production/durable_postgres/scripts/`:

- `list_quarantined.py` — `--limit 50 --offset 0 --format {table,json}`. Calls `dw.list_quarantined()`. Default `table` format. No mutation.
- `requeue_run.py` — **`--dry-run` is default; `--apply` opts in.** Arg: `--run-id <id>`. Reads checkpoint, prints `QuarantineSummary` + the prospective `requeue_count`, refuses apply if count ≥ 3. Calls `dw.requeue(token)` on `--apply`.
- `quarantine_delete.py` — **`--dry-run` default; `--apply` opts in; `--confirm <run_id>` mandatory match.** Hard-deletes the checkpoint via `store.delete(run_id)`. Refuses if `status != "quarantined"` (prevents wrong-row deletion). Prints summary + asks for `--confirm <id>` to match the row being deleted.

Optimistic-concurrency pattern: each script reads → confirms status → writes (or deletes) in one library call. The library method's `store.write()` carries the integrity_tag recompute; concurrent operator races result in last-write-wins on `requeue`, which is acceptable (idempotency check D-QUARANTINE-3 catches the double-requeue).

### D-QUARANTINE-7: Alert rule template — three rules

Add to `examples/production/durable_postgres_otel/alerts.yml`:

1. **`QuarantineSizeGrowing`** — `rate(durable_quarantine_size[15m]) > 0` for 30m → warning. Catches the "100 bad inputs land that week" failure mode in the gap doc.
2. **`QuarantineSizeOverThreshold`** — `durable_quarantine_size > 10` → warning; `> 100` → critical. Matches the gap doc's threshold.
3. **`RequeueLoopDetected`** — `rate(durable_requeue_total[1h]) by (run_id) > 3` → critical (insider hammering a poisoned run, or buggy retry loop). Requires emitting a `durable_requeue_total` counter labeled by `run_id` in S2 — coordinate with Tier 1.1 metrics extension.

### D-QUARANTINE-8: Healthcheck remains in-memory `quarantine_size` AND adds `persisted_quarantine_count`

Backward compat: keep existing `quarantine_size` (process-local fast counter). Add `persisted_quarantine_count: int` — call `len(await store.list_by_status("quarantined"))` (cached 60s to avoid hammering store). The two numbers should converge after daemon warms up; divergence > 10 for > 5m signals scheduler / store skew (alert candidate, not in initial rule set).

### D-QUARANTINE-9: Public API + pin

Three new methods on existing `DurableWorkflow` class (already in `__all__`). One new dataclass `QuarantineSummary` — **D-API-3 review required for `__all__` export** per Tier 2.2. Recommend exporting from `core.durable.workflow` not from top-level package (`adv_multi_agent.durable.QuarantineSummary`), matches `RunOutcome` placement.

The Tier 2.2 public-API pin test snapshots `__all__` set + load-bearing callable kwargs — adding three methods on `DurableWorkflow` does NOT trigger pin failure (method-level snapshotting is out of scope per D-BUDGET-5 precedent). Adding `QuarantineSummary` to `__all__` DOES — update pin in same PR.

---

## 4. Invariants

1. **`status != "quarantined"` raises `RuntimeError` on `requeue()`.** No silent recovery.
2. **`status in {completed, vetoed, quarantined}` raises on `quarantine()`.** No double-quarantine, no resurrection of terminal runs.
3. **Audit row appended every successful `quarantine` and `requeue`.** Post-hoc reconstruction; compliance.
4. **`list_quarantined()` returns ONLY allowlisted columns.** No `last_request_json`, no `pause_context`, no `rounds_history` body. PII discipline.
5. **`requeue` refuses at requeue_count ≥ 3.** Loop detection; fail-closed.
6. **`resume(token)` rejects `status="quarantined"` with `RunNotResumable`.** Cannot skip the audit gate.
7. **`quarantine_delete` requires `--confirm <run_id>` match AND `status=="quarantined"`.** No wrong-row deletion, no live-run deletion.
8. **Status flip + integrity tag recomputation = single `store.write()` transaction.** Same atomicity guarantee as `acknowledge_budget_exceeded` (Tier 2.3).

---

## 5. Attack surface

| Surface | Threat | Mitigation |
|---|---|---|
| Insider re-queues a poisoned run repeatedly to mask data exfil / cost burn | Hammers Anthropic/OpenAI; pollutes ledger | Fail-closed at requeue_count=3 (D-QUARANTINE-3) + `RequeueLoopDetected` alert (D-QUARANTINE-7 rule 3) |
| `list_quarantined` output ships to monitoring / Slack / pager | PHI / PII in `last_request_json` leaks to low-trust surface | Allowlist columns in `QuarantineSummary` (D-QUARANTINE-4); deep audit goes through `read_checkpoint` which is higher-trust |
| Insider deletes quarantined evidence to hide exploit attempt | Audit trail lost | `quarantine_delete` is logged at INFO with `run_id` + `reason` from the deleted summary BEFORE the store.delete call; deployment ships application-level log shipping per Tier 1.1 |
| Operator types wrong `run_id` in delete | Healthy run destroyed | `--confirm <run_id>` mandatory match + status guard `status=="quarantined"` (D-QUARANTINE-6) |
| Raw operator SQL flip `status='paused'` bypassing requeue | IntegrityViolation on next read (Tier 1.9 seal) | Already mitigated; methods exist so operators don't attempt raw edits |
| Two daemons race-quarantine the same run | Both call `quarantine()`; double audit row | First write wins on optimistic concurrency; second raises `RuntimeError` (D-QUARANTINE-2 step 1 — status already `quarantined`); benign |
| Operator calls `requeue` then `resume` on still-broken run | Re-crashes; scheduler re-quarantines | Loop detection (D-QUARANTINE-3); after 3 cycles operator MUST cancel or delete |

---

## 6. Failure modes

| Failure | Behavior |
|---|---|
| Inner workflow still crashes after requeue | Scheduler re-quarantines; new `quarantined` event row carries `requeue_count` incremented. After 3 cycles `requeue()` raises. |
| Operator deletes wrong row | Refused: `--confirm` must match AND status must be `"quarantined"` (cannot delete a live `running` or `paused` row via this script — use `cancel` instead). |
| Store.write fails mid-quarantine | In-memory `cp.status` modified but not persisted; on-disk row unchanged. Scheduler retries on next poll, hits same failure, eventually retries the quarantine call. Idempotent at the *attempt* level (target state is unchanged). |
| `list_quarantined` against store with 100k rows | Pagination caps response at `limit` (default 50). No streaming required at POC scale; document upgrade path in runbook. |
| Healthcheck `persisted_quarantine_count` query slow | 60s cache (D-QUARANTINE-8). Stale by definition; alert rules already use 15m / 30m windows so cache lag is acceptable. |
| Scheduler crashes mid-quarantine call | In-memory `_failures` count lost; persisted status unchanged. Next daemon start re-observes failures from zero; takes `max_retries=3` cycles to re-quarantine. Acceptable — re-quarantine is idempotent. |
| Operator runs `requeue` script while daemon happens to be processing a different status flip for same run | Library method's `store.write()` is atomic; one wins, the other raises `RuntimeError` on stale-status check. Operator retries. |

---

## 7. File layout

```
src/adv_multi_agent/core/durable/
  checkpoint.py        ADD "quarantined" to _STATUS_VALUES
  workflow.py          ADD: async def quarantine(self, token, reason)
                       ADD: async def requeue(self, token)
                       ADD: async def list_quarantined(self, *, limit, offset)
                       ADD: @dataclass(frozen=True) class QuarantineSummary
                       UPDATE: __all__ exports QuarantineSummary
  scheduler.py         CHANGE: on max_retries, call dw.quarantine(token,
                       reason="scheduler:max_retries") BEFORE _quarantine.add()
  store.py (Protocol)  ADD: async def list_by_status(self, status: str,
                       *, limit, offset) -> list[Checkpoint]
                       (MemoryCheckpointStore + FileCheckpointStore +
                        PostgresCheckpointStore implementations)

tests/unit/durable/
  test_workflow.py     EXTEND: ~10 tests
                       - quarantine happy path
                       - quarantine refuses on completed/vetoed/quarantined
                       - requeue happy path
                       - requeue refuses on non-quarantined status
                       - requeue fail-closed at count=3
                       - resume refuses on quarantined
                       - list_quarantined returns only allowlisted columns
                       - list_quarantined pagination
                       - end-to-end through EncryptedCheckpointStore
                       - scheduler integration: max_retries triggers persisted quarantine

examples/production/durable_postgres/scripts/
  list_quarantined.py  NEW — --limit/--offset/--format
  requeue_run.py       NEW — --dry-run default, --apply, --run-id
  quarantine_delete.py NEW — --dry-run default, --apply, --confirm <run_id>

examples/production/durable_postgres/daemon.py
examples/production/cipher_gcp_kms/daemon.py
examples/production/durable_postgres_otel/daemon.py
                       ADD healthcheck field: persisted_quarantine_count (60s cache)

examples/production/durable_postgres_otel/alerts.yml
                       ADD 3 alert rules: QuarantineSizeGrowing,
                       QuarantineSizeOverThreshold, RequeueLoopDetected
                       (third rule depends on durable_requeue_total counter —
                       wire in same PR or note dep on Tier 1.1 metrics)

docs/runbooks/durable-operations.md
                       ADD §6: "Quarantine recovery" — 5 sub-flows (list,
                       inspect, requeue, delete, alert) + code skeleton
                       + decision tree (requeue vs delete vs cancel)

docs/superpowers/specs/
  2026-05-18-quarantine-design.md  this doc
```

---

## 8. Decision rows (append to `docs/decisions.md` on implementation)

- D-QUARANTINE-1: `"quarantined"` is a status value, not a separate column (reuses Tier 1.9 seal + Tier 2.3 precedent)
- D-QUARANTINE-2: `quarantine(token, reason)` — atomic flip + audit row + reseal; rejects terminal states
- D-QUARANTINE-3: `requeue(token)` — flips to `paused`; fail-closed at requeue_count ≥ 3; explicitly non-idempotent
- D-QUARANTINE-4: `list_quarantined()` returns PII-redacted `QuarantineSummary` (allowlist) — deep audit via existing `read_checkpoint`
- D-QUARANTINE-5: `resume()` rejects `quarantined` status; requeue is the only gate
- D-QUARANTINE-6: Three operator scripts; all `--dry-run` default; delete requires `--confirm <run_id>` match + status guard
- D-QUARANTINE-7: Three alert rules — growth-rate, threshold, requeue-loop
- D-QUARANTINE-8: Healthcheck adds `persisted_quarantine_count` (60s cache) alongside existing in-memory `quarantine_size`
- D-QUARANTINE-9: `QuarantineSummary` export requires D-API-3 pin update; method additions do not

---

## 9. Out of scope

- Shared dead-letter store across deployments (per-deployment ownership remains the convention)
- GUI / dashboard for quarantine review (alert + CLI is sufficient for POC)
- Cursor-based pagination (offset-based fine at POC scale)
- Auto-requeue on schedule (operator decision, not library policy)
- Quarantine reason enum / taxonomy (free-form string; revisit if patterns emerge)
- Cross-tenant quarantine isolation (Tier 2.1 prerequisite, same defer as D-BUDGET-4)
- Quarantine-as-a-separate-Protocol (`QuarantineStore`) — reuses `CheckpointStore` via `list_by_status` extension

---

## 10. Effort — 2-slice arc

**Slice 1 (S1) — durability + library API, ~0.8d:**
- `_STATUS_VALUES` add + checkpoint test (0.05d)
- `DurableWorkflow.quarantine` / `requeue` / `list_quarantined` + `QuarantineSummary` (0.25d)
- `CheckpointStore.list_by_status` + 3 impls (Memory, File, Postgres) (0.2d)
- Scheduler integration — call `quarantine` on max_retries (0.1d)
- 10 unit tests + 1 end-to-end (0.2d)

**Slice 2 (S2) — operator dressing, ~0.6d:**
- Three scripts (list, requeue, delete) — mirror `reseal_all_checkpoints.py` pattern (0.2d)
- `persisted_quarantine_count` in three daemon healthchecks + cache (0.1d)
- Three alert rules in `alerts.yml` + `durable_requeue_total` counter wiring (0.15d)
- Runbook §6 rewrite + decision rows + NEXT_SESSION + commit (0.15d)

**Total:** ~1.4d. Below the gap doc's 3–4d estimate because the in-memory scheduler quarantine already exists — the lane is *persistence + operator surface*, not *invent quarantine*.

Slices are independently shippable: S1 closes the durability gap and the scheduler stops losing quarantines across restarts; S2 closes the operator-workflow gap. Recommend shipping S1 first as a standalone commit, then S2 in a follow-up — keeps PR blast radius small and lets the persisted-status migration soak before the operator scripts depend on it.
