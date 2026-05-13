# Workflows — retro-spec (2026-05-12)

Retro-spec for the three workflows shipped in the initial implementation: `AutoReviewLoop` (Workflow 2), `IdeaDiscovery` (Workflow 1), and `RebuttalWorkflow` (Workflow 4). All are async, subclass `BaseWorkflow`, and return `WorkflowResult`.

---

## What shipped

### BaseWorkflow (`src/workflows/base.py`)

- **Dependency injection:** accepts `executor`, `reviewer`, `ledger`, `wiki` at construction; creates defaults from `Config` if omitted.
- **Abstract contract:** `async def run(self, **kwargs) -> WorkflowResult`.

### AutoReviewLoop (`src/workflows/review_loop.py`)

- **Loop:** executor generates → reviewer scores → revise. Repeats up to `Config.max_review_rounds`.
- **Convergence:** `review.score >= config.score_threshold` (early exit) OR exhausted max rounds.
- **Claims extraction:** parses `## Claims` section from executor output; registers each line to `ClaimLedger`.
- **Self-improvement proposals:** parsed from `## Self-Improvement Proposals` section. Stored in wiki as `IMPROVEMENT` kind. Auto-approved iff `review.approved` is True for the same round; otherwise rejected.
- **Wiki feedback:** every review's critique is written to wiki as `FEEDBACK` entry.
- **`round_num` guard:** initialized to `0` before the loop (LL 2026-05-12 fix).

### IdeaDiscovery (`src/workflows/idea_discovery.py`)

- **Three phases:** lit survey (executor) → novelty check (reviewer as LLM, not as scorer) → proposal (executor).
- **Wiki integration:** survey stored as `LITERATURE`, novelty check as `NOTE`, proposal as `HYPOTHESIS`.
- **Reviewer role:** used via `reviewer.run()` (raw LLM call), not `reviewer.review()` (structured scoring) — appropriate since novelty check doesn't need a 0-10 score.
- **Section extraction:** `_extract_section()` splits on `## Candidate Directions` and stops at the next `##` section.
- **Output:** one-page research proposal. `final_score=0.0` — downstream `AutoReviewLoop` handles scoring.

### RebuttalWorkflow (`src/workflows/rebuttal.py`)

- **Four stages:** triage (executor) → draft rebuttal (executor) → adversarial check (reviewer) → finalise (executor, only if issues found).
- **Stage 4 conditional:** `final_output` is pre-set to `draft` before the conditional; stage 4 only runs if `len(issues) > 0`. Both paths reach `WorkflowResult`.
- **Issues parsing:** `_parse_issues()` tries `json.loads()` then regex-extracted JSON, then returns `[]`. Never raises.

---

## Invariants enforced (× attack surface)

| Invariant | Workflow.run() call | Direct BaseWorkflow subclass instantiation | Enforcement |
|---|---|---|---|
| Convergence: score threshold OR max rounds | AutoReviewLoop.run() checks both | Same — loop is inside `run()` | Score check inside loop; `range(1, max_review_rounds+1)` is the hard cap |
| `round_num` not unbound after empty range | `round_num = 0` before loop | Same | Sentinel initialization (LL 2026-05-12) |
| Self-improvement proposals stored before adoption | Proposals written to wiki; approval/rejection same round | Same | `wiki.add_improvement()` always called before `approve_improvement()` |
| `final_output` always assigned in rebuttal | Pre-set to `draft` before conditional stage 4 | Same | Initialization before the `if issues:` branch |
| `IdeaDiscovery` returns a proposal, never empty | Three phases all await responses before returning | Same | Sequential awaits; no early return before all three phases complete |
| Reviewer structured scoring only in AutoReviewLoop | `reviewer.review()` (returns `ReviewResult`) | Same | IdeaDiscovery uses `reviewer.run()` (raw); only AutoReviewLoop uses `reviewer.review()` |

---

## Files

```
src/workflows/base.py               BaseWorkflow, WorkflowResult
src/workflows/review_loop.py        AutoReviewLoop
src/workflows/idea_discovery.py     IdeaDiscovery
src/workflows/rebuttal.py           RebuttalWorkflow
```

---

## Known gaps / V1 followups

- **Self-improvement proposals auto-approved on score threshold.** `review.approved` (score >= threshold) triggers both loop convergence AND improvement adoption. A borderline-passing review (e.g. 8.0/10) can auto-adopt improvements that a stricter reviewer would reject. These are separate decisions: convergence (is the output good enough?) and adoption (should the process change?). Add a separate `reviewer.approve_improvement(proposal_text) -> bool` call with a higher threshold (or explicit human approval).
- **No claim deduplication.** Each round's executor output re-extracts `## Claims` from scratch. If the executor repeats the same claim across revisions, the ledger accumulates duplicates. Add a `text`-based dedup check in `_extract_and_register_claims()`.
- **`IdeaDiscovery` `final_score=0.0` is misleading.** Callers who chain `IdeaDiscovery` into `AutoReviewLoop` and check `result.final_score` from the discovery phase will see `0.0` and may interpret it as failure. Either omit the score field or set it to `None`.
- **No Manuscript workflow (Workflow 5).** ARIS §4.3 describes a full manuscript assurance workflow that chains `AutoReviewLoop → ClaimVerifier → ScientificEditor`. Not implemented. See build-plan Phase 3.
- **Rebuttal `rounds` count is hardcoded (3 or 4)** rather than reflecting actual stages run. If stage definitions change, the hardcoded count will silently drift. Derive from a stage counter instead.
- **No timeout on individual rounds.** An executor call that hangs (no API timeout set — see agents gap) will block the entire workflow indefinitely. Separate per-round timeout needed.

---

## Cross-references

- [docs/decisions.md](../decisions.md) — #7 (dual convergence criterion).
- [docs/superpowers/specs/2026-05-12-core-agents-retro.md](2026-05-12-core-agents-retro.md) — agents consumed by all workflows.
- [docs/superpowers/specs/2026-05-12-persistence-retro.md](2026-05-12-persistence-retro.md) — ledger/wiki consumed by AutoReviewLoop.
- [docs/superpowers/specs/2026-05-12-assurance-retro.md](2026-05-12-assurance-retro.md) — ClaimVerifier consumed post-loop.
