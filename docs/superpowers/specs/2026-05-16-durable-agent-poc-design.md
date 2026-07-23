# Durable long-running agent POC — design

**Date:** 2026-05-16
**Status:** Approved, ready for implementation plan
**Concrete target:** `ClinicalTrialEligibilityWorkflow` (healthcare domain) wrapped via `DurableWorkflow`
**Scope:** ~800 LOC under `core/durable/` + ~40 tests + 1 example script + SECURITY_MODEL row + D-DURABLE-1 decision

---

## Goal

Extend `core/` with a durable-execution layer that lets any `AdversarialWorkflow` pause for days-to-weeks and resume without losing context. Ship as a composition wrapper, not a parallel framework. Concrete validation target: `ClinicalTrialEligibilityWorkflow` with 3 named pause points covering rolling clinical data, human-approver SLA, and regulatory-clock pauses.

## Wedge vs. generic durable-execution frameworks

Generic durable-execution exists (Temporal, Restate, Inngest, AWS Step Functions, LangGraph checkpointing). The wedge here is **agent-native + adversarial-pattern-native**:

- Executor + reviewer state both checkpointed; ledger + wiki are already the durable substrate.
- Checkpoint stores a *compacted brief* (rounds_history), not a full transcript replay log — cheaper resume, smaller drift surface.
- Pause semantics are domain-shaped: clinical-trial data, regulatory clocks, approver SLAs — named gates, not "pause anywhere."
- Reconciliation hook is a first-class Protocol — generic frameworks treat tool-side state drift as caller's problem with no seam.

---

## Section 1 — Architecture & module layout

```
src/adv_multi_agent/core/durable/
├── __init__.py          # Public surface: DurableWorkflow, ResumeToken, BudgetExceeded, ReconciliationHook
├── workflow.py          # DurableWorkflow — composition wrapper over any AdversarialWorkflow
├── checkpoint.py        # CheckpointStore Protocol + FileCheckpointStore + Checkpoint dataclass
├── token.py             # ResumeToken dataclass + serialization
├── budget.py            # BudgetTracker + BudgetSnapshot + price table
├── scheduler.py         # SchedulerBackend Protocol + PollingScheduler + SchedulerDaemon
└── hooks.py             # ReconciliationHook Protocol + NoOpReconciliationHook + reference impls
```

**Invariants this layout enforces:**
- Composition not inheritance — wraps any existing `AdversarialWorkflow` unchanged. Healthcare/retail/PC/industrial workflows do not move.
- Checkpoint store sibling of `ClaimLedger` / `ResearchWiki` — atomic-write pattern (`atomic_write_text`), path-traversal guards (`safe_resolve_path` confines under `Config.workspace_dir`).
- Scheduler optional and isolated — explicit-resume callers ignore it.
- No magic: every pause is explicit `await ctx.pause(...)`, a budget breach, or a reviewer-veto.

**Public surface — 4 names total:** `DurableWorkflow`, `ResumeToken`, `BudgetExceeded`, `ReconciliationHook`.

---

## Section 2 — Core data shapes

### `ResumeToken`

```python
@dataclass(frozen=True)
class ResumeToken:
    run_id: str                    # uuid4 hex
    workflow_class: str            # fully-qualified import path
    pinned_executor_model: str
    pinned_reviewer_model: str
    schema_version: int            # bump on incompatible Checkpoint shape changes
    created_at: str                # ISO-8601 UTC
    wake_at: str | None            # ISO-8601 UTC; None = explicit-resume only
```

Returned by every `start()` / `pause()` / `resume()` call. Caller persists this; library does not own caller-side token storage.

### `Checkpoint`

Persisted to `<workspace>/checkpoints/<run_id>.json` via `FileCheckpointStore`:

```python
@dataclass
class Checkpoint:
    run_id: str
    schema_version: int
    status: Literal["running", "paused", "completed", "vetoed", "budget_exceeded", "failed"]
    round: int                     # 0-indexed; which review round we're on
    rounds_history: list[dict]     # per-round: executor draft, reviewer critique, score, flags
    last_request_json: str         # serialized *Request (caller can rehydrate on resume)
    pause_reason: str | None       # "rolling_data" | "approver_sla" | "regulatory_clock" | "budget" | None
    pause_context: dict            # caller-supplied free-form
    budget_used: BudgetSnapshot
    pinned_executor_model: str
    pinned_reviewer_model: str
    created_at: str
    updated_at: str
```

### `BudgetSnapshot`

```python
@dataclass(frozen=True)
class BudgetSnapshot:
    tokens_in: int
    tokens_out: int
    usd_spent: float               # 4-decimal precision; computed from per-model price table
```

### `ReconciliationHook` Protocol — see Section 4.

**Key choices:**
- `schema_version` on both `ResumeToken` and `Checkpoint`. Mismatch raises explicitly; never silent-restart.
- `rounds_history` is full audit trail — matches L-IND-2 invariant (preserve pre-veto drafts).
- Budget caps optional but warning-logged when omitted — fail-loud-by-default.

---

## Section 3 — Control flow

### Entry points

```python
class DurableWorkflow:
    def __init__(
        self,
        inner: AdversarialWorkflow,
        config: Config,
        checkpoint_store: CheckpointStore,
        budget_tracker: BudgetTracker | None = None,
        reconciliation_hook: ReconciliationHook | None = None,
        run_lock: RunLock | None = None,
        checkpoint_cadence: Literal["per_round", "per_pause", "per_call"] = "per_round",
    ): ...

    async def start(self, request: Any) -> RunOutcome: ...
    async def resume(
        self,
        token: ResumeToken,
        fresh_inputs: Any | None = None,
        force_model_upgrade: bool = False,
    ) -> RunOutcome: ...
    async def cancel(self, token: ResumeToken, reason: str) -> None: ...
```

### `RunOutcome`

```python
@dataclass
class RunOutcome:
    status: Literal["completed", "paused", "vetoed", "budget_exceeded", "failed"]
    token: ResumeToken
    result: WorkflowResult | None     # "completed" / "vetoed"
    pause_reason: str | None          # "paused"
    error: str | None                 # "failed"
```

### `start(request)` flow

1. Generate `run_id` (uuid4). Capture pinned models from `config`.
2. Acquire `RunLock` for `run_id` (no-op for `start()` since `run_id` is new; defensive).
3. Write initial checkpoint (`status="running"`, `round=0`).
4. Modified review loop:
   - Each round: executor call → budget check → reviewer call → budget check → flag/veto evaluation.
   - At configured cadence: persist updated checkpoint atomically.
   - If `inner` calls `ctx.pause(reason, context, wake_at=None)`: write `status="paused"`, release lock, return `RunOutcome(status="paused", ...)`.
   - If `BudgetExceeded` raised: write `status="budget_exceeded"`, release lock, re-raise wrapped in `RunOutcome`.
   - If converges: write `status="completed"`, release lock, return result.
5. Return `RunOutcome`.

### `resume(token, fresh_inputs, force_model_upgrade)` flow

1. Acquire `RunLock` for `token.run_id`. If already locked, raise `RunLocked`.
2. Load checkpoint by `token.run_id`. Validate `schema_version` matches; mismatch raises `SchemaVersionMismatch`.
3. Validate checkpoint `status == "paused"`. Other states raise `RunNotResumable(current_status)`.
4. Validate pinned models still resolvable. If `force_model_upgrade=False` and pinned model is retired → raise `ModelRetired`. If `True` → swap to current `Config` model, log swap into `rounds_history`.
5. Call `reconciliation_hook.on_resume(run_id, checkpoint, fresh_inputs)` with timeout `Config.reconciliation_timeout_seconds` (default 30s). Get back the request to execute against.
6. Continue review loop from `checkpoint.round`. Same loop body as `start()`.
7. Return `RunOutcome`.

### `cancel(token, reason)` flow

Mark checkpoint `status="failed"`, write `error=reason`. Idempotent — call on terminal checkpoint is no-op.

### Scheduler (optional, separate process)

`SchedulerDaemon(checkpoint_store, workflow_factory, poll_interval_seconds=60).run_forever()`:
- Polls store every N seconds, finds `status="paused"` + `wake_at <= now`.
- Calls `resume(token)` via factory-built workflow instance.
- Factory pattern: caller supplies `Callable[[str], DurableWorkflow]` keyed on `workflow_class` so daemon doesn't import every domain.
- Concurrent-safe via `RunLock`.

### `ctx.pause()` injection

- `AdversarialWorkflow.run()` gains optional `ctx: PauseContext | None = None` kwarg (backward compatible — existing workflows ignore it).
- `PauseContext.pause(reason, context, wake_at=None)` raises internal `_PauseSignal` caught by `DurableWorkflow`.
- ClinicalTrialEligibility example adds 3 named pause gates.

---

## Section 4 — Reconciliation hook contract

### Why it exists

A run paused 14 days ago resumes against a world that has moved. Lab values updated, insurer responded, IRB approved a protocol amendment, patient withdrew consent. The library cannot know which happened — only the caller can. The hook is the single seam where caller-owned freshness logic plugs in.

### Protocol

```python
class ReconciliationHook(Protocol):
    async def on_resume(
        self,
        run_id: str,
        checkpoint: Checkpoint,
        caller_supplied_fresh_inputs: Any | None,
    ) -> Any:
        """Return the *Request object the next review round will execute against.

        Invariants the hook MUST uphold:
        1. Return type matches the *Request dataclass of the wrapped workflow.
           Type-mismatch raises at the boundary before any model call.
        2. Idempotent: calling twice with same checkpoint + fresh_inputs
           returns equal objects. Library may call multiple times under
           scheduler retry; non-idempotent hooks corrupt state.
        3. May not perform writes the workflow itself owns (ledger, wiki,
           checkpoint). Read-only against agent state; free to read/write
           caller-owned external state.
        4. Should complete in < Config.reconciliation_timeout_seconds
           (default 30s). Past timeout → ResumeFailed raised; checkpoint
           remains 'paused', caller retries.
        """
```

### Default impl — `NoOpReconciliationHook`

Deserializes `checkpoint.last_request_json` back to the workflow's `*Request` type and returns it unchanged. Safe when inputs are immutable (e.g., regulatory-clock pause with no new data). Used when caller passes `reconciliation_hook=None`.

### Reference impls (under `examples/healthcare/reconciliation_hooks.py`)

1. **`MergeFreshInputsHook`** — takes `fresh_inputs` from the resume call, validates against `*Request` schema, returns it. For rolling-clinical-data: caller fetches new lab values, builds new `ClinicalTrialEligibilityRequest`, passes via `resume(token, fresh_inputs=new_request)`.

2. **`RehydrateFromCallbackHook`** — caller passes `async (run_id) -> Request` callback at construction. Hook ignores `fresh_inputs`, always calls the callback. For approver-SLA: hook hits approval DB, builds fresh request from current row.

3. **`AppendFreshContextHook`** — pulls original request from checkpoint, appends `fresh_inputs` to a designated free-text field (e.g., `member_history`), returns merged request. For audit-trail cases where prior context must be preserved.

### Failure modes

- Hook raises → checkpoint stays `"paused"`, error logged into `rounds_history`, `RunOutcome.status="failed"` with `error` populated.
- Hook returns wrong type → `TypeError` raised at boundary before any agent call.
- Hook returns request with `_MAX_FIELD_CHARS` violations → fields are silently truncated by the per-field `[:cap]` slice in `to_prompt_text`; execution continues. (A `cap_field` warning helper was added 2026-05-16 to make this observable and deleted 2026-07-23 with zero callers — the truncation is still silent. See D-DEPTH-3 and the L-IND-5 row in `SECURITY_MODEL.md`.)

### Security note

Hook is caller-trusted code. A malicious hook can inject prompt content into the next round. This is the same trust boundary as original `Request` construction — library does not widen the attack surface, but extends it across time. Documented in `SECURITY_MODEL.md` (new row).

---

## Section 5 — Failure modes & error handling

| # | Failure | Detection | Handling | Recovery |
|---|---|---|---|---|
| 1 | **Checkpoint write fails mid-round** | `OSError` from `atomic_write_text` | Re-raise; round work lost; in-memory state still valid | Caller retries `start()`/`resume()`; idempotent on `run_id` |
| 2 | **Checkpoint file corrupt at resume** | `JSONDecodeError` on load | Raise `CheckpointCorrupt(run_id, path)`; do NOT silently restart | Caller inspects, recovers-from-backup or abandons |
| 3 | **Schema version mismatch** | Version compare at load | Raise `SchemaVersionMismatch(found, expected)` | Caller upgrades or runs migration tool (deferred) |
| 4 | **Pinned model retired** | API model-not-found | Raise `ModelRetired(pinned, current_default)` unless `force_model_upgrade=True` | Caller abandons, or resumes with override (logged into `rounds_history`) |
| 5 | **Budget exceeded mid-call** | `BudgetTracker.check()` past cap | Persist `status="budget_exceeded"`, raise wrapped in `RunOutcome` | Caller raises cap and resumes, or cancels |
| 6 | **Reconciliation hook raises / times out** | Try/except + `asyncio.wait_for` | Log into `rounds_history`; checkpoint stays `"paused"`; return `RunOutcome(status="failed")` | Caller fixes hook, calls `resume()` again — checkpoint unchanged |
| 7 | **Agent API timeout / network error** | Existing `Config.request_timeout_seconds` | Checkpoint persisted at last-completed round; exception wrapped in `RunOutcome(status="failed")` | Caller retries `resume(token)` — picks up at `checkpoint.round` |
| 8 | **Concurrent resume of same run_id** | `RunLock` (atomic-rename `<run_id>.lock`) | Second caller raises `RunLocked(run_id, locked_by, locked_at)` | Caller retries after lock TTL (default 5min); stale locks reclaimed via mtime |

### Explicit non-handling

- Distributed multi-process scheduler — single-process POC scope.
- Partial-round atomicity inside a single agent call — mid-stream failure loses that draft; matches existing `AdversarialWorkflow` posture.
- Replay determinism — agent calls are non-deterministic; resume is forward-only from last checkpoint, never replays past calls.
- Cost-tracking across runs — `BudgetTracker` is per-run; org-wide caps belong in caller's billing layer.

### Logging

Each terminal state writes one structured log line: `run_id, status, rounds_completed, duration_s, tokens_in, tokens_out, usd_spent, pause_reason`. No PHI in logs — matches healthcare workflow posture.

---

## Section 5.5 — Scalability path (extension seams, no rewrite)

### Three abstractions are pluggable from POC day one

POC ships file-backed impls. Production swaps without touching `DurableWorkflow`, `ResumeToken`, or any wrapped workflow.

### 1. `CheckpointStore` Protocol

```python
class CheckpointStore(Protocol):
    async def write(self, checkpoint: Checkpoint) -> None: ...
    async def read(self, run_id: str) -> Checkpoint: ...
    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]: ...
    async def delete(self, run_id: str) -> None: ...
```

- POC impl: `FileCheckpointStore` — atomic JSON under `workspace/checkpoints/`. Mirrors `ClaimLedger`.
- Production swaps: `PostgresCheckpointStore` (one table, `run_id` PK, JSONB column, B-tree index on `(status, wake_at)`), `S3CheckpointStore`, `DynamoCheckpointStore`. Same Protocol, no caller change.

### 2. `RunLock` Protocol

```python
class RunLock(Protocol):
    async def acquire(self, run_id: str, ttl_seconds: int) -> LockHandle: ...
    async def release(self, handle: LockHandle) -> None: ...
    async def heartbeat(self, handle: LockHandle) -> None: ...
```

- POC impl: `FileRunLock` — atomic-rename `<run_id>.lock`, single-process.
- Production swaps: `PostgresAdvisoryLock` (`pg_try_advisory_lock(hashtext(run_id))`), `RedisRunLock` (Redlock), `DynamoConditionalLock`. Multi-process / multi-node safe.

### 3. `SchedulerBackend` Protocol

```python
class SchedulerBackend(Protocol):
    async def schedule_wake(self, token: ResumeToken, wake_at: datetime) -> None: ...
    async def poll_ready(self, batch_size: int) -> list[ResumeToken]: ...
```

- POC impl: `PollingScheduler` — single-process loop over `CheckpointStore.list_paused()`.
- Production swaps: `CeleryBeatScheduler`, `TemporalScheduler`, `AWSEventBridgeScheduler`, `PostgresPgBossScheduler`. Same Protocol.

### Scale levers wired in but not strained at POC

| Concern | POC posture | Scale path |
|---|---|---|
| Concurrent runs | Bounded by file-handle count | Postgres store → 100K+ concurrent paused runs |
| Throughput | Single Python process | `DurableWorkflow` stateless across calls → N workers pull from shared store |
| Run isolation | `workspace_dir` path | Multi-tenant: prefix store keys by `tenant_id`; store impl partitions transparently |
| Observability | Structured log lines | `MetricsBackend` Protocol (out of POC, named as future seam) — same pattern, callers plug in OTel/Prometheus |
| Schema migration | `schema_version` field reserved | Migration tool iterates `CheckpointStore.list_all()`, applies transform; storage-backend agnostic |

### What POC does NOT do, but abstractions reserve room for

- Sharded scheduler (multiple scheduler processes coordinating via `RunLock`) — works once `RunLock` is `PostgresAdvisoryLock`.
- Event-driven resume (resume on Kafka message instead of timer) — `SchedulerBackend.poll_ready()` is one impl; event-driven impl satisfies same Protocol.
- Cross-region replication — `CheckpointStore` impl owns this; library is indifferent.

### Rewrite-vs-extend rule

Anything that changes `Checkpoint` shape, `ResumeToken` shape, or the three Protocols above bumps `schema_version`. Anything else is an internal impl change. If `DurableWorkflow.start()` signature changes, that's the rewrite line — the design is shaped so it should not change just because storage moved from files to Postgres.

### Failure mode the abstraction prevents

Baking `FileCheckpointStore` semantics into `DurableWorkflow` (path strings, sync-file-locks, file-mtime as timestamp). POC tests use `MemoryCheckpointStore` precisely to force the abstraction — if a test passes against `MemoryCheckpointStore`, the abstraction is real, not file-shaped.

---

## Section 6 — Testing strategy

### Layer 1 — Protocol contract tests (~15 tests, `tests/unit/durable/test_protocols.py`)

Parametrized fixture runs same suite against `FileCheckpointStore` AND `MemoryCheckpointStore`. Forces abstraction to hold.

- `test_write_then_read_roundtrips`
- `test_list_paused_filters_by_wake_at`
- `test_delete_idempotent`
- `test_read_missing_raises_RunNotFound`
- `test_concurrent_writes_last_wins`
- `RunLock`: acquire / release / heartbeat / ttl-expiry / double-acquire-blocks
- `SchedulerBackend`: schedule + poll + batch-size-bounded

### Layer 2 — DurableWorkflow unit tests (~18 tests, `tests/unit/durable/test_workflow.py`)

`FakeExecutor` / `FakeReviewer` + `MemoryCheckpointStore`.

- `test_start_converges_returns_completed_outcome`
- `test_start_pauses_returns_pause_token_with_checkpoint_persisted`
- `test_resume_continues_from_checkpoint_round`
- `test_resume_with_fresh_inputs_passes_to_hook`
- `test_resume_with_NoOpHook_uses_stored_request`
- `test_resume_rejects_schema_version_mismatch`
- `test_resume_rejects_unknown_run_id`
- `test_resume_rejects_non_paused_status`
- `test_pinned_model_used_on_resume_by_default`
- `test_force_model_upgrade_swaps_model_and_logs`
- `test_budget_exceeded_persists_checkpoint_and_raises`
- `test_budget_exceeded_then_resume_with_raised_cap_continues`
- `test_reconciliation_hook_raises_marks_failed_keeps_paused_checkpoint`
- `test_reconciliation_hook_timeout_marks_failed`
- `test_reconciliation_hook_wrong_return_type_raises_TypeError`
- `test_cancel_marks_failed_idempotent`
- `test_concurrent_resume_second_caller_raises_RunLocked`
- `test_checkpoint_cadence_per_round_writes_once_per_round`
- `test_checkpoint_cadence_per_call_writes_twice_per_round`

### Layer 3 — Integration tests (~7 tests, `tests/integration/test_durable_clinical_trial.py`)

Real `ClinicalTrialEligibilityWorkflow` wrapped, fakes for executor/reviewer, file-backed store under `tmp_path`.

- `test_three_pause_point_rolling_data_resumes_correctly`
- `test_scheduler_daemon_wakes_paused_run_at_wake_at`
- `test_veto_in_durable_run_persists_first_draft` (L-IND-2 holds under durability)
- `test_bias_flag_round1_to_round2_resume_preserves_flag_history`
- `test_phi_not_written_to_checkpoint_json_in_plain_form` (sanitization holds; checkpoint stores already-sanitized fields only)
- `test_resume_after_schema_version_bump_with_migrator_succeeds`
- `test_full_lifecycle_start_pause_resume_pause_resume_complete`

### Test fixtures (`tests/unit/durable/fakes.py`)

- `MemoryCheckpointStore`, `MemoryRunLock`, `MemorySchedulerBackend` — in-process Protocol impls.
- `RecordingReconciliationHook` — captures every call for assertion.
- `BudgetExceededExecutor` — wraps `FakeExecutor` to force `BudgetExceeded` on the Nth call.

### Out of POC test scope

- Live API calls (existing repo convention)
- `PostgresCheckpointStore` / `RedisRunLock` impls (Protocol-contract test suite is the spec they must satisfy later)
- Multi-process scheduler races (single-process POC)
- Performance benchmarks (premature; real Postgres impl gates load tests)

**Coverage:** 100% on `core/durable/*.py`. Mypy `--strict` + ruff clean. All existing 558 tests must still pass — `DurableWorkflow` does not modify wrapped workflows.

---

## Section 7 — Out-of-scope / known gaps

Each documented in `SECURITY_MODEL.md` Known Gaps table on ship:

| Gap | Why deferred | Surfacing |
|---|---|---|
| Distributed scheduler (multi-process / multi-node) | Single-process scheduler validates abstraction; distributed is impl swap | Protocol shape supports it |
| Postgres / Redis / S3 store impls | POC ships `FileCheckpointStore` + `MemoryCheckpointStore`; production impls follow | Protocol-contract test suite is the spec |
| Schema migration tooling | `schema_version` field reserved; migration tool is separate ship | First version bump triggers the build |
| `MetricsBackend` Protocol (OTel / Prometheus / Datadog) | Structured logs cover POC observability | Named in design, not coded |
| Cross-region replication | `CheckpointStore` impl concern | Documented |
| Replay determinism | Agent calls non-deterministic; forward-only resume | Explicit posture, not a gap |
| Partial-round atomicity inside a single agent call | Mid-stream executor failure loses that draft — matches existing `AdversarialWorkflow` | Inherited |
| Live API integration tests | Existing repo convention | Inherited |
| Cost-tracking across runs | Per-run only; org-wide caps in caller's billing layer | Documented |
| Audit log of checkpoint mutations | `rounds_history` is audit trail; separate append-only log is future work | Documented |

### Carried-over invariants (must hold under durability — verified in integration tests)

- `metadata['first_draft']` preserved on veto (L-IND-2)
- `sanitize_for_prompt` on caller-supplied fields (M-PC-1 + healthcare PHI posture)
- `_MAX_FIELD_CHARS = 1500` per-field cap (L-PC-3)
- `truncate_flag_display` re-injection cap = 16 (L-PC-5)
- `extract_veto_directive` line-anchored regex + sibling-stop (M-PC-1 + H-IND-1)
- Score threshold 8.0 healthcare / 7.5 elsewhere (D-HEALTH-2)
- PHI = caller's responsibility; checkpoint never widens this surface (D-HEALTH-3)
- Regulator-specific veto language (D-HEALTH-4)

### New invariant introduced by durability (D-DURABLE-1)

A paused run's checkpoint contains only already-sanitized request data — never raw caller input. Sanitization happens at `*Request.to_prompt_text()` time, *before* the first checkpoint write. Checkpoint is downstream of sanitization, never upstream.

---

## Concrete deliverable

`ClinicalTrialEligibilityWorkflow` wrapped in `DurableWorkflow` with 3 named pause points:
1. **Post-criteria-eval** — pause if eligibility-criteria evaluation indicates labs incomplete (rolling-data trigger)
2. **Post-bias-check** — pause if bias-gate flags require IRB / sponsor sign-off (approver-SLA trigger)
3. **Post-evidence-review** — pause for FDA 21 CFR 312 regulatory window if adverse-event signal detected (regulatory-clock trigger)

Demonstrated via `examples/healthcare/clinical_trial_durable.py` showing start → pause → resume → pause → resume → complete lifecycle with synthetic de-identified data and `MergeFreshInputsHook`.

## Scope summary

- ~800 LOC new code under `core/durable/`
- ~40 new tests (15 protocol + 18 unit + 7 integration)
- 1 example script (`examples/healthcare/clinical_trial_durable.py`)
- 1 SECURITY_MODEL row (D-DURABLE-1 + hook trust-boundary note)
- 1 decisions.md row (D-DURABLE-1)
- 1 README + CLAUDE.md + architecture.md update (mention new capability)

**Out of scope:** see Section 7.
