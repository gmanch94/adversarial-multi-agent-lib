# Architecture depth review — 2026-07-23

**Scope:** whole-`src/` standing-back review of the 63-workflow surface, lensed on **module depth** (leverage behind a small interface) and **locality** (does a change land in one place?). Complements — does not repeat — the 16 security/correctness audit cycles and the [2026-07-18 holistic implementation review](2026-07-18-holistic-implementation-review.md), which used a convention-coherence + test-quality lens and closed F1/F2.

**Method:** conformance sweep of all 64 workflow modules against the D-IND-1 recipe; deletion test applied to every shared static; census of the flag-header handling conventions; census of metadata-scalar sanitization; dead-symbol scan of `core/_internal.py`. Every finding is a counted census, not a sample.

**Grading:** blast-radius at the current stage — pre-launch pip-installable template, no live users. Nothing here is a live security defect.

---

## Verdict

**The spine is deep; the rim has drifted.** `core/_internal.py` is doing its job — `extract_flags` / `extract_veto_directive` / `truncate_flag_display` are genuinely deep modules (one regex change closed H-IND-1 across every domain), and the M-PC-1 / H-IND-1 hoists are correctly load-bearing. No CRITICAL / HIGH.

But **three independent conventions** now exist for the same job at the workflow rim, and the newest domains adopted the *shallowest* one. The result is a stringly-typed interface where the same flag-header literal is hand-synced across five call sites per file, and an 18-file class where the declaration that *looks* load-bearing is dead.

| # | Sev | Depth issue | Files | One-liner |
|---|-----|-------------|-------|-----------|
| **D1** | MEDIUM | stringly-typed flag interface + dead declaration | 18 | `_FLAG_HEADERS` declared then never referenced; the real strings hardcoded at 5 sites. Editing the tuple changes nothing. |
| **D2** | MEDIUM | veto output composition diverged semantically | 25 → 2 behaviours | 7 workflows never render the veto directive into `output`; 18 put it up top. Same seam, two contracts. |
| **D3** | LOW-MED | metadata scalars unsanitized in the 3 older domains | 28 sites | L-HEALTH-2 was fixed for healthcare only; retail/pc/industrial still pass raw `request.field`. |
| **D4** | LOW | `cap_field` is a deep helper with **zero** callers | 1 def, 0 uses | The L-IND-5 silent-truncation fix shipped, was documented as the new convention, and was never adopted — including by 27 later workflows. |
| **D5** | LOW | `_extract_veto` is a pure pass-through | 25 | Fails the deletion test outright; justified only by "Test API preserved". |
| **D6** | — | **ADR-blocked, not proposed** | 64 | 5208 lines of `run()` loop. See "Considered and rejected". |

---

## Resolution — 2026-07-23 (D1 + D2 + D3 + D4 applied; D5 deferred; D6 stays rejected)

Scope confirmed with the user before touching anything — D1/D2 change convergence-gate and veto-output code, which CLAUDE.md's fold-in policy routes to surface-and-confirm rather than silent fold-in.

- **D1 fixed — 18 files converged onto convention A.** healthcare 4 (`adverse_event_triage`, `clinical_trial_eligibility`, `drug_interaction_flagging`, `treatment_plan_review`) + lifesciences 14. Each now drives `current` / `accumulated` from `{h: [] for h in _FLAG_HEADERS}`, extracts via `for header in _FLAG_HEADERS:`, gates on `not any(current.values())`, and passes `accumulated` straight to its checklist builder. `_format_flag_section` takes the dict and reads a `banner` map. Net: the tuple is load-bearing in all 51 declaring modules; the five hand-synced sites collapse to two (tuple + banner map). Convention C (5 files, no tuple) left as-is — lower priority, and those at least carry no lying declaration.
- **D2 fixed — all 25 veto workflows on variant A.** The 7 draft-first files (retail `recall_scope`; pc `claims_reserve`, `coverage_decision`, `environmental_impairment`, `gig_platform_liability`; industrial `product_liability_root_cause`, `recall_scope_manufacturing`) now render `VETO DIRECTIVE: {veto_reason}` above the vetoed draft. All 25 `_compose_output` bodies are now byte-identical (verified by hashing each body: 2 distinct → 1). Banners left unchanged — variant-A files already carried the same "See metadata['veto_reason']" phrasing, so this is the minimum behaviour-focused diff.
- **D3 fixed — 28 metadata scalars sanitized** across industrial 8 / pc 8 / retail 12, matching the healthcare + lifesciences form `sanitize_for_prompt(request.<field>, max_chars=200)`.
- **D4 — `cap_field` deleted** (user chose delete over adopt-across-58). The unused `warnings` import went with it. **This forced a false-closure fix:** `SECURITY_MODEL.md:95` claimed L-IND-5 was *"Closed 2026-05-16"* on the strength of a helper with zero callers — the exact comment-asserted-safety failure mode `LESSONS_LEARNED.md` names. That row is now **Open**, stating the real posture and what closing it would actually take.
- **D5 deferred** — the 25 `_extract_veto` pass-throughs are cosmetic; left for the next touch of those files.
- **D6 not attempted** — ADR-blocked (see below).

### The durable half — [`tests/unit/test_workflow_conventions.py`](../../tests/unit/test_workflow_conventions.py)

Per-instance fixes are linear whack-a-mole; the guard retires the class. Four AST-level cross-domain guards, **+192 tests**:

| Guard | Asserts | Retires |
|---|---|---|
| **G1** | a module declaring `_FLAG_HEADERS` references it ≥2× | the dead-declaration trap (D1) |
| **G2** | every `extract_flags` header literal ∈ that module's `_FLAG_HEADERS` | the fail-open rename path (D1) |
| **G3** | every veto `_compose_output` interpolates `veto_reason` into a returned string | the invisible-directive split (D2) |
| **G4** | no metadata dict value is a bare `request.<attr>` | unsanitized scalars (D3) |

Plus `test_veto_workflow_census_is_stable` — recomputes the veto count from source rather than trusting prose, so adding a veto workflow forces a re-read of G3.

**All four were mutation-tested** — each bug shape was reintroduced and the corresponding guard confirmed red, then reverted. This matters here specifically: the first G3 mutation attempt silently failed to apply and the guard "passed", which would have read as a weak guard. A guard that has never been observed failing is not evidence.

**Gate:** ruff (src + tests) · mypy strict, 111 files · **1449 tests** (was 1257) · 26 skipped (modules with no `_FLAG_HEADERS`, by design).

Two defects were caught during the sweep by mypy and a per-workflow test — a stale leftover parameter in `field_action_classification._format_flag_section` — not by the full suite passing. Consistent with the verification note below.

---

## D1 — MEDIUM — the flag-header interface is stringly-typed, and 18 declarations are dead

**What.** Three conventions coexist for "which flag headers does this workflow parse?":

| Convention | Count | Domains | `_FLAG_HEADERS` |
|---|---|---|---|
| **A — dict-driven** | 33 | retail 5, pc 5, industrial 6, healthcare 4, lifesciences 13 | load-bearing |
| **B — named-locals + dead tuple** | 18 | healthcare 4, lifesciences 14 | **declared, never referenced** |
| **C — named-locals, no tuple** | 5 | retail 1, pc 2, industrial 2 | absent |

Convention A makes the tuple the single source of truth:

```python
current: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
accumulated: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
...
for header in _FLAG_HEADERS:
    current[header] = extract_flags(review.critique, header)
    accumulated[header].extend(current[header])
```

Convention B declares the identical tuple and then ignores it — `ccds_label_change.py:77-81` declares `_FLAG_HEADERS`, and the body re-hardcodes all three literals:

```python
current_signal_flags   = extract_flags(review.critique, "SAFETY-SIGNAL FLAGS:")          # :320
current_regional_flags = extract_flags(review.critique, "REGIONAL-DIVERGENCE FLAGS:")    # :321
current_clock_flags    = extract_flags(review.critique, "IMPLEMENTATION-CLOCK FLAGS:")   # :324
```

**Why this is a depth problem, not a style problem.** In convention B each header literal must agree across **five** hand-synced sites in the same file: the `extract_flags` call, the `_format_flag_section` banner dict, the `accumulated` dict keys passed to the checklist builder, the `_build_*_checklist` `.get(...)` lookups, and the reviewer-criteria prompt template. The interface a maintainer must hold in their head is as large as the implementation — the definition of a **shallow** module. Convention A collapses four of those five onto one tuple.

**Failure scenario (the reason this is MEDIUM).** A maintainer renames a flag header — say `IMPLEMENTATION-CLOCK FLAGS:` → `NOTIFICATION-CLOCK FLAGS:` — edits `_FLAG_HEADERS` because that is what the file presents as the declaration, updates the prompt template, and ships. `extract_flags` still searches for the old literal, finds nothing, returns `[]`. The convergence gate `and not current_clock_flags` is now **permanently satisfied**: the workflow converges while silently never enforcing that flag class. Every existing test stays green — they assert on the *presence* of flags they inject under the header the test itself hardcodes.

This is a fail-**open** path on the convergence gate, which is what separates it from the fail-safe over-collection cases the 2026-07-18 review graded LOW.

**No justification for B exists.** The obvious hypothesis — "veto workflows need named locals because the veto check interleaves with flag extraction" — is **false**. `pc/workflows/environmental_impairment.py:348` and `gig_platform_liability.py:360` are both veto workflows using `for header in _FLAG_HEADERS:` with `self._extract_veto(...)` eleven lines later. Convention A demonstrably supports the veto path. B is drift, not design.

**Fix.** Converge the 18 B-files onto convention A. The dead tuple becomes load-bearing; four of the five sync points collapse. Deletes the named locals (6 per file: `current_*` + `all_*` × 3). Convention C (5 files) is the same change but the tuple must be added — lower priority, they at least don't carry a lying declaration.

**Do not fix by deleting the dead tuple.** That is the tempting cheap move and it is backwards: it discards the declaration and blesses the shallow shape.

---

## D2 — MEDIUM — the veto seam has two contracts

**What.** All 25 veto workflows carry a `_compose_output` static. It collapses to exactly two distinct bodies:

**Variant A — 18 files** (healthcare 4, lifesciences 14) — banner first, **directive verbatim in the output**:

```python
return (
    f"{_VETO_BANNER}\n\nVETO DIRECTIVE: {veto_reason}\n\n"
    f"--- Vetoed draft below ---\n\n{draft}\n\n---\n\n{_DISCLAIMER}"
)
```

**Variant B — 7 files** (retail 1, pc 4, industrial 2) — draft first, banner as a footer, **`veto_reason` never rendered**:

```python
return f"{draft}\n\n---\n\n{_VETO_BANNER}\n\n{_DISCLAIMER}"
```

Variant B's banners then instruct the reader to go find it themselves — verbatim from `pc/workflows/claims_reserve.py`:

> `"⚠️  REVIEWER VETO — workflow halted before convergence. See metadata['veto_reason']. Escalate to senior actuary / claims committee immediately; do not book this reserve."`

**Why this matters.** These are the seven highest-stakes halts in the library — reserve booking, coverage denial, food recall scope, product-liability root cause, manufacturing recall scope. On exactly those, the human-readable `output` shows the full un-vetoed draft first and defers the *reason for the halt* to a dict key the reader has to know to inspect. An approver who reads `result.output` — the obvious thing to read — gets the draft plus a pointer.

D-RETAIL-1 (which established the veto pattern) requires capturing the veto verbatim in `metadata['veto_reason']` and prepending a banner. Both variants satisfy the letter. Variant A satisfies the intent.

**Fix.** Standardize on variant A. Per `autonomy.md` (security > durability), surfacing the halt reason to the human beats terseness. This is a **behaviour change on 7 safety-path workflows** — output-format tests will need updating — so it needs explicit sign-off, not a fold-in.

**Depth note.** Once the bodies agree, `_compose_output` is 25 copies of one function differing only by two module constants — a shared `compose_veto_output(draft, veto_reason, banner, disclaimer)` in `core/_internal.py` passes the deletion test (delete it and the same logic reappears 25 times) and gives the seam one owner.

---

## D3 — LOW-MED — 28 metadata scalars bypass sanitization in the older three domains

**What.** `LESSONS_LEARNED.md` records L-HEALTH-2: *"audit caught raw `request.field[:200]` metadata scalars — a defensibility concern... 7 fixes across 7 workflows."* That fix landed in healthcare only. The lesson generalizes; the remediation did not.

Healthcare + lifesciences now do this (`ccds_label_change.py:364`):

```python
"product_description": sanitize_for_prompt(request.product_description, max_chars=200),
```

Retail, pc, and industrial still do this — **28 sites**, uncapped and unsanitized:

```python
"component_summary": request.component_summary,   # industrial/make_vs_buy.py:317
"loss_event": request.loss_event,                 # pc/claims_reserve.py:420
"supplier_lot": request.supplier_lot,             # retail/recall_scope.py:354
```

Full census: industrial 8, pc 8, retail 12.

**Why LOW-MED, not MEDIUM.** No exploit path — this is `WorkflowResult.metadata`, not a prompt. It is a *defensibility* and belt-and-suspenders-convention gap of the same shape L-HEALTH-2 already graded and fixed, plus an unbounded-growth path (a caller passing a 2 MB field gets it echoed whole into metadata).

**Fix.** Mechanical: wrap all 28 in `sanitize_for_prompt(..., max_chars=200)`. Behaviour-visible only for inputs >200 chars or containing control characters.

---

## D4 — LOW — `cap_field` has zero callers

**What.** `core/_internal.py:194` defines `cap_field(value, max_chars, field_name)` — caps a Request field and emits a `UserWarning` on truncation. Its docstring says:

> *"Existing workflows that use `value[:_MAX_FIELD_CHARS]` directly remain correct but silent. New workflows should use this helper."*

Census: **1 occurrence in `src/`** — the definition. **0 callers. 0 tests.** Meanwhile **58 workflows** use `cap = _MAX_FIELD_CHARS` + raw `value[:cap]`, including all 27 lifesciences workflows, every one of which shipped *after* `cap_field` existed.

This is the comment-asserted-convention failure mode CLAUDE.md names by name: a docstring declaring a convention with nothing enforcing it. `cap_field` was the L-IND-5 remediation for the concern `LESSONS_LEARNED.md` describes as *"a regulator asks 'what was the AI's actual input?' and the answer is 'the first 1500 chars of each field'"*.

**Fork — this is a user call, not a fold-in:**
- **Adopt** — route all 58 `to_prompt_text` methods through `cap_field`. Delivers the L-IND-5 defensibility win the helper was written for. Touches prompt construction in every workflow; adds a `UserWarning` on oversized input that some tests may need to expect.
- **Delete** — remove the helper and the docstring claim. Honest, one-line, abandons the improvement.

Leaving it as-is is the one option with no upside: the repo carries a documented convention that nothing follows.

---

## D5 — LOW — `_extract_veto` fails the deletion test

25 identical statics whose entire body is a delegate:

```python
@staticmethod
def _extract_veto(critique: str, max_chars: int) -> str | None:
    """Thin delegate to `core._internal.extract_veto_directive`
    (M-PC-1 / M2 / L5 hardening). Test API preserved."""
    return extract_veto_directive(critique, "REVIEWER VETO:", max_chars)
```

Delete it and no complexity reappears — call sites call `extract_veto_directive` directly. The sole justification is the docstring's "Test API preserved", i.e. the tests reach for the private static rather than the shared helper, which is itself the coupling worth removing. Genuinely cosmetic; bundle it with D2 (same 25 files) or skip it.

---

## Considered and rejected

**D6 — shared run-loop / workflow base class. ADR-blocked; not proposed.**

The census is real: `async def run()` spans **5208 lines across 64 workflows** (mean 81), and the loop skeleton — round loop → build prompt → `executor.run` → `_register_claims` → `reviewer.review` → extract flags → `wiki.add_feedback` → veto check → convergence check — is structurally identical everywhere.

It stays rejected. **D-RETAIL-7**, **D-IND-1**, and **D-LIFESCI-1** all lock "no domain base class", and D-RETAIL-7's reasoning survives this census intact: the rejection was about the *configuration surface* (per-flag-header banner text, metadata key names, per-scenario checklist text, veto presence, flag-class count, request-dataclass shape), and that surface exists whether it is injected into a base class or passed to a shared `run_adversarial_loop(...)`. Line count is not the argument; the injection-point count is, and it is unchanged. Fixing D1 shrinks the per-file body materially without touching this.

Recorded here so the next depth review does not re-derive it. If it is ever reopened, it needs a new ADR row, not a fold-in.

## Verification note

Per finding F2 of the 2026-07-18 review, **26 of 44** unit-test files still assert flags with `assert any(substr in f ...)`. A convention refactor can therefore change behaviour while the suite stays green. D1 and D2 must be verified by exact-equality assertions or fixture-output diffing — "1257 tests pass" is not evidence for these two.
