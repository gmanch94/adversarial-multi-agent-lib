# Budget recovery — design (Tier 2.3, advisor-revised closing-the-loop cut)

**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Driver:** `docs/production-readiness-gaps.md` §2.3
**Advisor revision:** original gap (`BudgetTracker.check_and_charge` raise + library catch + status flip) is ALREADY SHIPPED. `BudgetTracker.record()` enforces caps; `DurableWorkflow.start`/`resume` catch `BudgetExceeded` and persist `status="budget_exceeded"`; `resume()` refuses non-paused status. Residual = the **recovery path** is undocumented and the existing runbook step 3 ("call `resume(token)`") is wrong (raises `RunNotResumable`).

---

## 1. Goal

Close the loop on already-shipped budget enforcement: ship an operator-facing recovery method + fix the runbook.

**Library impact:** one new public async method on `DurableWorkflow`. No Protocol changes; no cipher seam; no checkpoint schema bump.

---

## 2. Forced-design constraint (probe result)

A regression probe confirmed: if the operator raw-edits `status="budget_exceeded"` → `"paused"` directly on the inner store (bypassing the library), the next `EncryptedCheckpointStore.read()` raises `IntegrityViolation` — the recomputed canonical hash no longer matches the integrity_tag encrypted at write time. **Therefore the recovery path MUST go through the library** so the flip + reseal happen atomically. Pure-runbook (operator-only) recovery is not viable post-Tier-1.9.

---

## 3. Locked design choices

### D-BUDGET-1: One narrow method — `acknowledge_budget_exceeded(token)`

```python
class DurableWorkflow:
    async def acknowledge_budget_exceeded(self, token: ResumeToken) -> None:
        ...
```

Contract:
1. Reads the checkpoint. Raises `RuntimeError` if `status != "budget_exceeded"` (not idempotent — surface unexpected state instead of silently passing).
2. Sets `status = "paused"`.
3. Appends `{"event": "budget_cap_acknowledged", "at": <ts>, "budget_used_at_ack": {...}}` to `rounds_history`. Auditable proof of the operator decision.
4. `await self._store.write(cp)` — which goes through `EncryptedCheckpointStore.seal()` → recomputes integrity_tag. Single transaction.

Caller still constructs a new `DurableWorkflow` with higher-capped `BudgetTracker` BEFORE calling this method. Method itself does NOT take a new-cap argument — the cap lives on the BudgetTracker in the constructed workflow; passing it here would couple library API to BudgetTracker internals + create two configuration surfaces for the same thing.

### D-BUDGET-2: Reject `resume_after_budget_exceeded(..., new_max_usd=...)` (advisor option 3)

Adding a full convenience that takes the cap inline would:
- Couple library API to BudgetTracker constructor kwargs (max_tokens_in, max_tokens_out, max_usd, future per-tenant caps)
- Create a code path an insider could call to bypass budget enforcement without constructing the higher-cap tracker visibly in deployment code
- Duplicate `resume()` semantics

Reject. Operators construct the higher-cap tracker themselves; library just unblocks the status gate.

### D-BUDGET-3: Audit row is mandatory, not optional

`rounds_history` gets the `budget_cap_acknowledged` event UNCONDITIONALLY. Compliance reviewers (21 CFR Part 11 / SOC 2) need to reconstruct cap-raise decisions years later. The row carries the budget snapshot at acknowledge time so they can compare against the next round's spend to verify the new cap was tight.

### D-BUDGET-4: Defer per-tenant budget enforcement (gaps doc explicit defer)

Gaps doc says "Per-tenant budget after 2.1 lands." Tier 2.1 (multi-tenant isolation) is not shipped. Per-tenant caps would require a tenant_id column + per-tenant BudgetTracker registry. Out of scope for this lane.

### D-BUDGET-5: Public API + signature pin

`acknowledge_budget_exceeded` is a method on the existing `DurableWorkflow` class (already in `__all__`). No new module-level export. The Tier 2.2 public API pin test (`test_public_api_stability.py`) does not currently snapshot DurableWorkflow methods individually — adding this method does NOT trigger the pin's failure mode (since the pin checks `__all__` set + load-bearing callables, not every method on every class).

Optional follow-up: extend the pin to cover `DurableWorkflow` public methods. Out of scope for this slice — the pin already catches the load-bearing failure mode (kwarg drift on construction).

---

## 4. Invariants

1. **`status != "budget_exceeded"` raises `RuntimeError`.** No silent pass; caller knows they're in the wrong state.
2. **Status flip + integrity tag recomputation = single `store.write()` transaction.** No window where status is updated but tag is stale.
3. **Audit row is appended every successful call.** Post-hoc reconstruction is possible.
4. **`resume(token)` works immediately after a successful acknowledge.** No additional state flips required.

## 5. Attack surface

| Surface | Threat | Mitigation |
|---|---|---|
| Insider calls acknowledge to bypass cap | Cap raise without going through deployment-level review | Method does NOT raise the cap. Caller MUST construct a new DurableWorkflow with a higher-cap BudgetTracker first. The cap-raise is visible in deployment code, not hidden inside a library call. |
| Raw operator SQL edit to status column | IntegrityViolation on next read | Already mitigated by Tier 1.9 integrity_tag; method exists so operators don't have to attempt the raw edit |
| Acknowledge on wrong status row | Operator wedges a healthy run | Method raises RuntimeError; healthy run is untouched (read+raise is read-only on the row) |
| Acknowledge race vs. concurrent resume | Both flip status; tag races | Method does NOT take the lock (it's pre-resume — operator action, not concurrent execution). If two operators acknowledge concurrently, last write wins on optimistic-concurrency terms; both audit rows are appended (one in each rounds_history snapshot, with the later one overwriting). Acceptable: cap-raise is rare + monitored. Production deployments should serialize operator console actions via their existing change-control. |

## 6. Failure modes

| Failure | Behavior |
|---|---|
| Operator forgot to raise cap on the new BudgetTracker | Next `record()` raises BudgetExceeded again; checkpoint flips back to `budget_exceeded`; operator sees the same state with a new `budget_cap_acknowledged` row in history (proof they tried) |
| Operator calls acknowledge then resume on a runaway loop | Resume runs; spends until new cap; flips back to budget_exceeded. Operator should `cancel(token)` if rounds_history indicates runaway, not acknowledge |
| Checkpoint read fails mid-acknowledge | RuntimeError propagates; no state change |
| Store.write fails after status flip | The in-memory `cp.status` was modified but never persisted; the on-disk row is still `budget_exceeded`. Next call retries cleanly. |

## 7. File layout

```
src/adv_multi_agent/core/durable/
  workflow.py          ADD: async def acknowledge_budget_exceeded(self, token)
                       (just above cancel())

tests/unit/durable/
  test_workflow.py     EXTEND: 3 tests (happy path, wrong status raises,
                       end-to-end through EncryptedCheckpointStore)

docs/runbooks/
  durable-operations.md  REWRITE §5.5: 4-step recovery flow + code skeleton
                         + audit-trail mention; correct the
                         "call resume(token)" mistake

docs/superpowers/specs/
  2026-05-18-budget-acknowledge-design.md  this doc
```

## 8. Decision rows

- D-BUDGET-1: Narrow `acknowledge_budget_exceeded(token)` method; library does atomic flip + reseal
- D-BUDGET-2: Reject `resume_after_budget_exceeded(new_max_usd=...)` convenience — couples API to BudgetTracker internals + bypass surface
- D-BUDGET-3: Mandatory audit row in rounds_history with budget snapshot
- D-BUDGET-4: Defer per-tenant budget enforcement until Tier 2.1 ships
- D-BUDGET-5: No public API pin change (method on already-public class)

## 9. Out of scope

- Per-tenant budget enforcement (Tier 2.1 prerequisite)
- New-cap-as-argument signature (D-BUDGET-2 reject)
- Auto-double-the-cap heuristic (operator decision, not library policy)
- Refund / negative-record on the BudgetTracker (out of POC scope; L-DUR-5 acceptable)
- Pin extension for DurableWorkflow methods (separate hygiene task)

## 10. Effort

Single slice, ~0.3d:
- workflow.py method + 3 tests: 0.15d
- Runbook §5.5 rewrite + spec + decisions + NEXT_SESSION + commit: 0.15d
