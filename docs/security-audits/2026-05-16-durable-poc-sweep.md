# 2026-05-16 PM — Durable agent POC security sweep

**Scope:** new `core/durable/` subpackage (~1100 LOC including tests) + `healthcare/workflows/clinical_trial_eligibility_durable.py`.

**Posture:** 0 CRIT · 4 HIGH · 6 MED · 5 LOW · 15 CLEAN.

**H-DUR-3 closed same-session** via `workspace_dir` kwarg on `FileCheckpointStore` + `FileRunLock` (commit `4ad2776`). H-DUR-1, H-DUR-2, H-DUR-4 documented as posture in `SECURITY_MODEL.md` §3 (commit `906fe2c`). MED/LOW tracked for follow-up.

---

## Files audited

- `src/adv_multi_agent/core/durable/workflow.py` — `DurableWorkflow`, `PauseContext`, `_PauseSignal`, `RunOutcome`, model-pin allowlist
- `src/adv_multi_agent/core/durable/checkpoint.py` — `Checkpoint`, `FileCheckpointStore`, `MemoryCheckpointStore`
- `src/adv_multi_agent/core/durable/token.py` — `ResumeToken`, serialization
- `src/adv_multi_agent/core/durable/lock.py` — `RunLock` impls, TTL, heartbeat
- `src/adv_multi_agent/core/durable/budget.py` — `BudgetTracker`, price table
- `src/adv_multi_agent/core/durable/hooks.py` — `ReconciliationHook` Protocol + 4 impls
- `src/adv_multi_agent/core/durable/scheduler.py` — `PollingScheduler`, `SchedulerDaemon`
- `src/adv_multi_agent/core/durable/protocols.py` — Protocols + `BudgetExceeded`
- `src/adv_multi_agent/healthcare/workflows/clinical_trial_eligibility_durable.py` — durable subclass

---

## CRITICAL

**None.** The two paths an attacker would attack first — checkpoint path-traversal and JSON deserialization gadgets — are defended adequately for a POC.

---

## HIGH

### H-DUR-1 — `_PauseSignal` swallows convergence/veto gates after mid-round pause

**File:** `core/durable/workflow.py` — `try / except _PauseSignal` block in start() + resume() round loops.

**Attack vector.** `PauseContext.pause()` raises `_PauseSignal`, which the durable loop catches outside the inner workflow's normal control flow. An inner `run_round()` that has executed an executor call but not yet a reviewer call can `await ctx.pause(...)` to halt before convergence/veto evaluation. On resume, the loop re-enters the next round from `prior_state = ps.context` — the previous round's reviewer verdict (including a VETO directive) is never enforced for that round.

**Impact.** Logic bypass of the adversarial-review invariant on resume. A malicious or buggy `run_round` can short-circuit veto gates by pausing post-executor-pre-reviewer.

**Severity:** HIGH (logic invariant; design contract under-specified).

**Status:** **DOCUMENTED POSTURE** in `SECURITY_MODEL.md` §3. Contract requires `pause()` only at end-of-round, after `rounds_history_entry` has been appended. Trial-durable subclass follows this contract.

**Future remediation:** on resume, replay prior round's reviewer state and re-check for unsatisfied veto in `cp.rounds_history` before invoking next `run_round`. Regression test: construct a `run_round` that pauses after critique containing `REVIEWER VETO:` and assert resume halts.

---

### H-DUR-2 — Reconciliation hook output bypasses request sanitization + field caps

**File:** `core/durable/workflow.py` `resume()` (hook invocation branch) + `core/durable/hooks.py` (all 4 impls).

**Attack vector.** On `start()`, parent workflow's `*Request.to_prompt_text()` enforces `_MAX_FIELD_CHARS = 1500` per field and runs `sanitize_for_prompt`. On `resume()`, request comes from `hook.on_resume(...)` — none of the four reference hooks re-validate cap, control chars, or dataclass-type identity beyond `MergeFreshInputsHook`'s `isinstance` check. Caller-supplied `fresh_inputs` carrying prompt-injection content lands in the next round.

**Impact.** Resumed run can carry larger or differently-shaped inputs than a fresh `start()` would accept. Sanitization happens at prompt-build time inside `to_prompt_text`, NOT at request-construction time — D-DURABLE-1's "sanitize upstream of checkpoint" claim is decorative on this path.

**Severity:** HIGH for HIPAA / regulated deployments; MEDIUM otherwise.

**Status:** **DOCUMENTED POSTURE** per D-DURABLE-2 — hook is caller-trusted Protocol. Trust boundary equal to original `Request` construction. Hook contract docstring states this explicitly.

**Future remediation:** add `_validate_request_shape(request, expected_type)` after `hook.on_resume(...)` asserting type identity, per-field length ≤ cap, and `sanitize_for_prompt` idempotence.

---

### H-DUR-3 — `FileCheckpointStore` / `FileRunLock` accept any `base_dir`; no sandbox

**Files:** `core/durable/checkpoint.py` `FileCheckpointStore.__init__`, `core/durable/lock.py` `FileRunLock.__init__`.

**Attack vector (pre-fix).** Both stores called `safe_resolve_path(Path(base_dir))` without `must_be_under=` — normalize but don't confine. A caller passing `base_dir` derived from untrusted input would silently get a store rooted anywhere on disk (`~/.ssh/`, `C:\Windows\System32\Tasks`, etc.). `_path` charset check (`run_id.replace("-","").isalnum()`) prevents traversal via run_id but does nothing about malicious base_dir.

**Impact.** Arbitrary file write of attacker-controlled JSON. With `O_CREAT|O_EXCL` semantics, scope is "create new files only" — but PHI / API-key-bearing checkpoints in `~/.ssh/` or a webroot is bad.

**Severity:** HIGH.

**Status:** **CLOSED** in commit `4ad2776`. Added optional `workspace_dir: Path | str | None` kwarg to both `__init__`s. When provided, `safe_resolve_path` called with `must_be_under=workspace_dir` — confines base_dir under workspace. When None, current behavior preserved but `UserWarning` emitted. Two dedicated warning-assertion tests added.

---

### H-DUR-4 — `Checkpoint.last_request_json` stores raw request (PHI bleed-through at rest)

**Files:** `core/durable/workflow.py` `_serialize_request` + all checkpoint writes.

**Attack vector.** `_serialize_request` does `json.dumps(asdict(request), default=str)` — no sanitization, no encryption, no PHI redaction. Result lands on disk in `FileCheckpointStore` for run lifetime + however long caller retains paused checkpoints. For trial-durable workflow: patient labs, demographics, criteria — all PHI under HIPAA. Any operator with FS access or backup pipeline sees raw PHI.

`sanitize_for_prompt` does not help — runs at prompt-build time, not request-checkpoint time.

**Impact.** PHI at rest in plaintext JSON. HIPAA breach surface if `FileCheckpointStore` used in production with PHI.

**Severity:** HIGH for healthcare; MEDIUM otherwise.

**Status:** **DOCUMENTED POSTURE** in `SECURITY_MODEL.md` §3 + §4 Known Gaps. D-HEALTH-3 extended across time. `FileCheckpointStore` is POC scope; healthcare deploys must (a) confine `workspace_dir` to encrypted volume (LUKS/BitLocker/EBS-encrypted), (b) ship `EncryptedFileCheckpointStore` decorator, or (c) use `PostgresCheckpointStore` with TDE.

---

## MEDIUM

### M-DUR-1 — `BudgetTracker.record` TOCTOU race + no integrity check on zero-reports

**File:** `core/durable/budget.py`.

`record` reads `self._tokens_in`, compares to cap, assigns. No `asyncio.Lock`. Shared tracker across concurrent runs → cap overshoot. Inner workflow that never calls `record()` → silent uncapped spend.

**Fix:** wrap `record` in `asyncio.Lock`; optional `expect_increments(min_per_round=1)` assertion.

### M-DUR-2 — `FileRunLock` stale-eviction race

**File:** `core/durable/lock.py`.

Window between `path.unlink()` (stale eviction) and `os.open(O_CREAT|O_EXCL)` (re-acquire). Mutual exclusion holds but error attribution misleading. Worse on fast-NFS / virtualized FS.

**Fix:** replace with `fcntl.flock` (POSIX) or `msvcrt.locking` (Windows). Or document File* impls are single-host-low-contention.

### M-DUR-3 — `ttl_seconds=0` / negative / huge accepted

**File:** `core/durable/lock.py`.

`_is_stale = (now - acquired_at) >= ttl_seconds`. ttl=0 → always stale → no mutex. ttl=`sys.maxsize` → wedged lock. No validation.

**Fix:** validate `1 <= ttl_seconds <= 86400` in both impls' `acquire`.

### M-DUR-4 — `_serialize_request` `default=str` silently lossy + injection surface

**File:** `core/durable/workflow.py`.

`json.dumps(..., default=str)` falls back to `str(obj)` for non-serializable types. Custom `__str__` with prompt-injection content lands in checkpoint. Round-trip lossy and silent (`Decimal`, `datetime`, `Path` → `str`).

**Fix:** drop `default=str`; require callers to pre-serialize exotic fields. Add round-trip identity test.

### M-DUR-5 — Checkpoint field types unvalidated; model swap re-check missing

**File:** `core/durable/checkpoint.py` + `workflow.py` `resume()`.

`_checkpoint_from_json` rejects unknown extras but doesn't validate field types. `pinned_reviewer_model` never checked against allowlist. After `force_model_upgrade` swap, `_model_is_available(cp.pinned_executor_model)` is not re-checked.

**Fix:** type-validate fields in `__post_init__`. Re-check allowlist after swap. Validate reviewer model.

### M-DUR-6 — `MemoryCheckpointStore.list_paused` Protocol-fidelity gap

**File:** `core/durable/checkpoint.py`.

`FileCheckpointStore.list_paused` filters on `wake_at <= wake_before`; need to verify `MemoryCheckpointStore` applies the same filter. If not, paused runs wake before scheduled time on Memory backend.

**Fix:** verify filter applies; add Protocol-fidelity regression test.

---

## LOW

### L-DUR-1 — `run_id` charset accepts Unicode via `str.isalnum`

`"٢ﾃ".isalnum() is True`. Library-internal use is safe (uuid4 hex). Caller-supplied IDs (tenant IDs, job IDs) can land Unicode in filenames → homoglyph collision on case-insensitive FS.

**Fix:** tighten to `re.fullmatch(r"[a-zA-Z0-9-]{1,64}", run_id)`.

### L-DUR-2 — `deserialize_token` validates schema but not field shape

Tampered `wake_at` (non-ISO) crashes `datetime.fromisoformat` later. Tampered `run_id` (path-traversal) caught by downstream `_path` charset, but defense-in-depth desirable.

**Fix:** validate `run_id` charset, ISO timestamps parseable, models in allowlist at deserialize time.

### L-DUR-3 — `atomic_write_text` lacks directory fsync on POSIX

File-content fsync happens, but directory-entry fsync after `os.replace` does not. Rare power-loss timing can roll back the rename.

**Fix:** add directory fsync on POSIX after replace. Document Windows semantics.

### L-DUR-4 — `SchedulerDaemon` lacks per-token error isolation

Factory raises → may crash daemon (starve remaining runs) or retry-spam (log DoS).

**Fix:** wrap per-token in try/except; quarantine after N retries.

### L-DUR-5 — `BudgetExceeded` mid-round → double-billing on resume

If raised after executor call but before reviewer call, partial round not in `rounds_history`. Resume with higher cap replays executor call → double-billing.

**Fix:** document contract OR sub-checkpoint after executor call.

---

## CLEAN — implemented correctly

A researcher would expect to find these broken; they are not:

1. **`_PauseSignal` is private** (underscore-prefixed, not in `__init__.py`). External code can't catch it to abuse; can only RAISE via `ctx.pause`, which is wrapped.
2. **`_path()` rejects path-traversal in `run_id`** — both stores enforce `run_id.replace("-","").isalnum()`. `"../etc/passwd"` rejected. Empty rejected.
3. **`_checkpoint_from_json` rejects unknown extra fields.** Strict-extra check prevents forward-compat smuggling.
4. **`Checkpoint.__post_init__` validates `status` enum.** Tampered status raises on load.
5. **`deserialize_token` rejects non-dict input.** No `pickle.loads`, no `eval`.
6. **`MemoryRunLock.release` checks `acquired_at` match.** Prevents another handle from releasing current holder.
7. **`FileRunLock` uses `O_CREAT|O_EXCL`** for atomic acquire.
8. **`force_model_upgrade=False` is default.** Resume against retired model raises `ModelRetired`; opt-in swap targets `Config.executor_model` not attacker-controlled string.
9. **`SchemaVersionMismatch` raises on load.** No silent migration.
10. **`BudgetTracker` no-caps construction emits `UserWarning`.** Fail-loud default.
11. **`atomic_write_text` is temp + fsync + os.replace.** No torn writes.
12. **`PollingScheduler.poll_ready` paginates via `batch_size`.** Bounded memory.
13. **Reconciliation hook is named Protocol with multiple impls.** Trust boundary explicit.
14. **`pinned_executor_model` is checkpoint-pinned**, not config-pinned at resume. Config drift can't silently change model.
15. **No `pickle`, `eval`, `exec`, `subprocess`, `os.system`, `shell=True`, dynamic `import_module(user_input)`** anywhere in the subpackage.

---

## SUMMARY TABLE

| # | Severity | Area | File | Status |
|---|----------|------|------|--------|
| H-DUR-1 | HIGH | `_PauseSignal` bypasses convergence/veto on resume | `core/durable/workflow.py` | DOCUMENTED |
| H-DUR-2 | HIGH | Reconciliation hook bypasses sanitization + field caps | `core/durable/workflow.py`, `hooks.py` | DOCUMENTED |
| H-DUR-3 | HIGH | `FileCheckpointStore` / `FileRunLock` accept any `base_dir` | `core/durable/checkpoint.py`, `lock.py` | CLOSED `4ad2776` |
| H-DUR-4 | HIGH | `Checkpoint.last_request_json` stores raw PHI at rest | `core/durable/workflow.py`, `checkpoint.py` | DOCUMENTED |
| M-DUR-1 | MEDIUM | `BudgetTracker.record` TOCTOU + no integrity check | `core/durable/budget.py` | OPEN |
| M-DUR-2 | MEDIUM | `FileRunLock` stale-eviction race | `core/durable/lock.py` | OPEN |
| M-DUR-3 | MEDIUM | `ttl_seconds=0` / negative / huge accepted | `core/durable/lock.py` | OPEN |
| M-DUR-4 | MEDIUM | `_serialize_request` `default=str` lossy + injection | `core/durable/workflow.py` | OPEN |
| M-DUR-5 | MEDIUM | Checkpoint field types unvalidated; swap re-check missing | `core/durable/checkpoint.py`, `workflow.py` | OPEN |
| M-DUR-6 | MEDIUM | `MemoryCheckpointStore.list_paused` Protocol-fidelity gap | `core/durable/checkpoint.py` | OPEN |
| L-DUR-1 | LOW | `run_id` charset accepts Unicode | `core/durable/checkpoint.py`, `lock.py` | OPEN |
| L-DUR-2 | LOW | `deserialize_token` shape validation | `core/durable/token.py` | OPEN |
| L-DUR-3 | LOW | `atomic_write_text` lacks directory fsync POSIX | `core/_internal.py` | OPEN |
| L-DUR-4 | LOW | `SchedulerDaemon` per-token error isolation | `core/durable/scheduler.py` | OPEN |
| L-DUR-5 | LOW | `BudgetExceeded` mid-round double-billing on resume | `core/durable/workflow.py` | OPEN |

---

## Cumulative posture (7 cycles)

Cycle 1 (2026-05-12, initial): 3C/6H/8M/6L all closed.
Cycle 2 (2026-05-13, retail): CRIT-free; LOW closed.
Cycle 3 (2026-05-14 AM, PC): 0C/0H/1M/5L all closed.
Cycle 4 (2026-05-14 PM, industrial): 0C/1H/0M/5L all closed.
Cycle 5 (2026-05-16, healthcare): 0C/0H/1M/4L all closed.
Cycle 6 (2026-05-16, healthcare follow-up): all carried forward closed.
**Cycle 7 (2026-05-16 PM, durable POC):** 0C/4H/6M/5L — 1H closed, 3H + all M/L documented as posture or tracked for follow-up.

**Recurring lesson:** convention-level error compounding remains the top failure mode. M-PC-1 (opening anchor) and H-IND-1 (closing sibling-stop) were the prior examples; H-DUR-3 (decorative `safe_resolve_path` call without `must_be_under=`) is the cycle-7 instance of the same shape. Shared helpers + load-bearing safety claims need enforcement at the call site, not in the docstring.
