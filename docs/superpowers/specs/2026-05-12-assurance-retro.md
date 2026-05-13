# Assurance layer — retro-spec (2026-05-12)

Retro-spec for `ClaimVerifier` (3-stage claim verification) and `ScientificEditor` (5-pass editing pipeline) shipped in the initial implementation.

---

## What shipped

### ClaimVerifier (`src/assurance/verifier.py`)

- **Stage 1 — Integrity:** executor checks all PENDING claims for internal contradictions. Returns a list of `{claim_a, claim_b, reason}` pairs.
- **Stage 2 — Result-to-claim mapping:** reviewer checks each claim individually: does the attached evidence actually support it? Returns `bool`.
- **Stage 3 — Adversarial audit:** reviewer scores the claim (0-10) and issues a verdict (`supported | disputed | retracted`). Uses `context[:2000]` of the document.
- **Ledger writes:** each stage resolves or disputes the claim in the ledger. Stage 2 failure short-circuits to dispute; stage 3 determines final status.
- **Early return:** if no PENDING claims, returns summary immediately from ledger state.
- **JSON parse fallback:** `_extract_json()` static method tries regex before failing gracefully on every parse site.

### ScientificEditor (`src/assurance/editor.py`)

- **Pass 1:** clutter removal (filler phrases, stacked hedges, redundancy).
- **Pass 2:** passive → active voice where subject is known and active is clearer.
- **Pass 3:** sentence structure (length, comma splices, pronoun antecedents).
- **Pass 4:** terminology consistency (defined terms, abbreviation first-use).
- **Pass 5:** numerical consistency (flag mismatches as `[MISMATCH: ...]`; no value changes).
- **Spot-check:** reviewer compares edited vs original; returns `introduced_errors`, `flags_needing_attention`, `readability_improved`.
- **Output:** `EditingReport` with `original`, `final`, `pass_outputs` dict (all 5 intermediate results), and spot-check fields.

---

## Invariants enforced (× attack surface)

| Invariant | Normal usage (via workflow) | Direct instantiation | Enforcement |
|---|---|---|---|
| 3 stages run in order (integrity → mapping → audit) | `verifier.verify()` calls stages 1→2→3 sequentially | Same — no way to call individual stages directly (private methods) | Stage methods are `_stage1_*`, `_stage2_*`, `_stage3_*` — not in public API |
| Stage 2 failure short-circuits to dispute (skip stage 3) | `if not mapped: ledger.dispute(); continue` | Same | `continue` in the loop after stage 2 failure |
| Stage 3 verdict drives ledger final status | `if verdict == "supported": ledger.resolve(SUPPORTED)` etc. | Same | Exhaustive `if/elif/else` covering all three verdict values |
| Pass 5 does NOT change values (annotate only) | Prompt instructs "DO NOT change values — only flag" | Same | Prompt-level instruction only — **not enforced programmatically** |
| All 5 passes run regardless of intermediate quality | Loop `for pass_num in range(1, 6)` | Same | No early exit in the pass loop |
| JSON parse never raises (always returns dict/list) | `_extract_json` + try/except at every call site | Same | Catch-all fallback returns safe default at every parse site |

---

## Files

```
src/assurance/verifier.py   ClaimVerifier, VerificationReport
src/assurance/editor.py     ScientificEditor, EditingReport
```

---

## Known gaps / V1 followups

- **Pass 5 "no value changes" is prompt-only, not enforced.** The instruction tells the executor not to change numerical values, but nothing programmatically prevents it. A post-pass diff check could detect mutations: compare all numbers in `pass_outputs[4]` (input to pass 5) vs `pass_outputs[5]` (output); raise or warn if values differ beyond annotation markers.
- **`context[:2000]` in stage 3 audit is a hard truncation.** A long document (50-page paper) will have its tail cut. Stage 3 reviewers may miss claims that rely on context past the first 2000 chars. Increase to a configurable limit, or use a document summary as context instead.
- **`_extract_json` regex `r"(\{.*\}|\[.*\])"` with DOTALL is greedy.** If model output contains two JSON objects (e.g. explanation + result), the regex matches from the first `{` to the last `}` — potentially including non-JSON text. Use a non-greedy match or a proper JSON parser (`json.JSONDecoder.raw_decode`).
- **Stage 1 integrity check uses executor, not reviewer.** ARIS §4.3 implies the integrity check should be adversarial (cross-model). Using the executor to check its own claims reduces the adversarial value. Move stage 1 to `self.reviewer.run()`.
- **No per-claim caching.** Each `verify()` call re-sends all PENDING claims through all three stages. If a run is interrupted and resumed, already-resolved claims are skipped (correct) but the stage 1 integrity check re-runs over all pending claims regardless. Consider caching the integrity check result in the wiki.
- **`ScientificEditor` has no input size guard.** A 100-page document passed to `editor.edit()` will exceed the context window for the pass prompts. Add a token-count check or chunking strategy before V1.
- **`EditingReport.pass_outputs` stores full text for all 5 passes.** For a 10K-word document, this is ~50K tokens of duplicated content in memory. Consider storing only diffs (pass N vs N-1) instead.

---

## Cross-references

- [docs/decisions.md](../decisions.md) — #2 (cross-model adversarial pairing, applies to stage 3 audit).
- [docs/superpowers/specs/2026-05-12-persistence-retro.md](2026-05-12-persistence-retro.md) — `ClaimLedger` consumed by `ClaimVerifier`.
- [docs/superpowers/specs/2026-05-12-core-agents-retro.md](2026-05-12-core-agents-retro.md) — agents consumed by both assurance components.
