# CGT/ATMP Ship Audit — 8 Cell & Gene Therapy lifesciences workflows

**Date:** 2026-07-25
**Scope:** `hctp_classification`, `cgt_potency_assay`, `cgt_comparability`, `donor_eligibility`, `cgt_durability_claim` (veto) · `rmat_designation`, `vector_safety`, `cgt_lot_release_spec` (no-veto) — modules, tests, examples, 32 skill templates, plus the shared spine they call.
**Method:** `security-audit` skill (independent general-purpose reviewer, briefed blind) + convention checks a–j from the batch-A/B audit template + independent runtime reproduction of the two top findings.
**Run mode:** scheduled, unattended. Mechanical fixes auto-applied and committed locally. **Nothing pushed.**

---

## Verdict

**FIX-BEFORE-SHIP** — but the blocking defect is **not CGT-specific**. The 8 new modules are convention-clean: every a–j check passes. The two findings that matter (**C-1**, **H-1**) are **shared-spine / shared-convention** defects that the CGT batch inherits along with all 30 veto workflows and all 71 workflows repo-wide. Both were reproduced live against this tree, not inferred.

Per-module CGT surface: **SHIP-CLEAN**. Spine: **FIX-BEFORE-SHIP**.

---

## Convention checks a–j — all PASS on the 8 modules

| # | Check | Result |
|---|---|---|
| a | 3 CRITICAL review dimensions ↔ exactly one `_FLAG_HEADERS` member each | PASS — 24/24 dimension↔header pairs 1:1; every header carries a `Flag under <HEADER>` line |
| b | Threshold parity, module criteria vs test config | PASS *with a domain-wide caveat* — 5 veto modules state `Score >= 8.0` (= `config.score_threshold`); 3 no-veto state `7.5`. That 7.5-for-no-veto pattern holds across **all 14** no-veto lifesciences modules, so it is a pre-existing domain convention, not a CGT defect. Direction is fail-closed. See **L-3**. |
| c | `wiki.add_feedback(...)` before `_extract_veto(...)` in each veto `run()` | PASS — hctp 322→373, potency 313→364, comparability 309→358, donor 305→356, durability 304→357 |
| d | Shared-helper inheritance; gate uses `_flag_classes_unresolved`, not bare `not any(...)` (D-A11-1) | PASS — all 8 route through `self._flag_classes_unresolved(...)`. The one `not any(...)` per module is in `_format_flag_section` (display short-circuit), not the gate |
| e | L-HEALTH-1 PHI comment on `first_draft` — only `donor_eligibility` | PASS — present only there (3 refs); correct given the Request field shapes (only donor screening/testing echoes individually identifiable history) |
| f | Boundary docstrings are real distinctions | PASS — 4 explicit D-LIFESCI-2 boundary blocks: potency vs `AssayPerformanceClaimWorkflow`, comparability vs `BiosimilarComparabilityWorkflow`, durability vs `PromotionalOffLabelReviewWorkflow`, donor vs healthcare `AdverseEventTriageWorkflow`; plus `vector_safety`'s no-veto-rationale block and `cgt_lot_release_spec`'s potency cross-ref |
| g | H-IND-1 header hygiene `^[A-Z][A-Z\s\-]*[A-Z]$` | PASS — 24/24 clean. `RCR-RCL-RISK FLAGS:` correctly uses hyphens where the prose is `RCR/RCL`. Zero digit-, slash-, or paren-containing headers; 361/351/1271/1394 appear only in prose/fields/criteria |
| h | Input bounding | PASS — per-field `[:cap]` with `_MAX_FIELD_CHARS = 1500` on every field of all 8 `to_prompt_text`; `sanitize_for_prompt(..., max_chars=6000)` post-concat; every metadata scalar via `sanitize_for_prompt(..., max_chars=200)`, zero bare `request.<field>` (L-HEALTH-2 clean). *Bounding is present and correct; the 6000 cap's **behaviour** is **H-1**.* |
| i | Flag-list tests assert `== [expected]` | PASS — zero `assert any(substr in f ...)` across the 8 test files. (Coverage caveat: only flag class #1 is equality-asserted — **L-4**) |
| j | No-brand (D-LIFESCI-3) | PASS — token scan over the 8 modules + 8 tests + 8 examples + 32 templates surfaces only regulatory acronyms (AAV, CAR-T category words, ELISA, LAL, LAM-PCR, VCN, SIN, IFN, EPCIS, GAMP, …), class names, and section headers. No product or company trade name. *Tripwire is a known-case guard, not proof.* |

**Prompt-injection surface:** every caller-pasted Request field flows through the per-field cap and then `sanitize_for_prompt` at the boundary; no field bypasses it. Reviewer-derived text is never re-injected raw (critique 4000, suggestions 500, prior output 10000, flags 500 × 16 via `truncate_flag_display`). No credentials anywhere in the 56 audited files. No caller-controlled path reaches the filesystem.

---

## Fixed automatically

Commit **`e1d9f71`** — `fix(lifesciences): CGT ship-audit mechanical fixes - decision-ID drift, donor PHI comment`. Gate green before and after.

### 1. Decision-ID drift after the D-LIFESCI-5/6 → 7/8 renumbering (LOW, 14 sites)

Commit `8c76bce` renumbered the CGT decisions but landed the change in the workflow modules only. The stale IDs did not dangle — they pointed at **real but wrong** decisions (D-LIFESCI-5/6 are the Phase-2 batch A/B build rows), so the audit trail asserted the wrong provenance for the CGT veto split.

Docstring / frontmatter-description text only. Zero behaviour change.

| File:line | Was | Now |
|---|---|---|
| `tests/unit/test_hctp_classification.py:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `tests/unit/test_cgt_potency_assay.py:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `tests/unit/test_cgt_comparability.py:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `tests/unit/test_donor_eligibility.py:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `tests/unit/test_cgt_durability_claim.py:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `tests/unit/test_rmat_designation.py:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `tests/unit/test_vector_safety.py:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `tests/unit/test_cgt_lot_release_spec.py:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `src/adv_multi_agent/lifesciences/skills/templates/hctp_review.md:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `…/templates/potency_review.md:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `…/templates/comparability_review.md:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `…/templates/donor_review.md:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `…/templates/durability_review.md:3` | D-LIFESCI-6 | D-LIFESCI-8 |
| `examples/lifesciences/hctp_classification.py:10` | D-LIFESCI-5 | D-LIFESCI-7 |

Mapping: **D-LIFESCI-7** = 5th-segment decision incl. the 361-scenario scoping; **D-LIFESCI-8** = the 5-veto / 3-no-veto split.

### 2. Missing L-HEALTH-1 PHI comment on the donor output path (LOW, 1 site)

`src/adv_multi_agent/lifesciences/workflows/donor_eligibility.py:388` (`_compose_output`).

`metadata['first_draft']` carries the L-HEALTH-1 caveat at `:339-343`, but the same donor screening/testing narrative is embedded **verbatim in `WorkflowResult.output`** on both the clean and the vetoed path — and that is the surface the example prints to stdout. Added the equivalent comment naming the downstream-handling obligation.

Comment only — the output string is unchanged. Adding a *caveat line to the output itself* would change behaviour and is escalated as **L-5**.

---

## Escalated for review

### CRITICAL

#### C-1 — Fail-OPEN flag + veto parse via a later line-anchored duplicate header block

> **STATUS: FIXED** (2026-07-25, after this report was filed) — occurrence *selection* replaced with union (`extract_flags`) / first-non-empty (`extract_veto_directive`) + per-occurrence section bounding. Locked as **D-A11-5**, which supersedes A11-M4. Guarded by `TestA11D5TrailingEchoCannotShadow` in `tests/unit/test_parser_hardening.py` and by a workflow-level regression in `tests/unit/test_hctp_classification.py::TestVeto::test_trailing_clean_echo_does_not_suppress_the_halt`. The `missing_flag_headers` echo-only residual is documented in that function's docstring and asserted by a test rather than left invisible. The original finding is preserved below unedited.


`src/adv_multi_agent/core/_internal.py:369-372` (`extract_flags`), `:480-484` (`extract_veto_directive`), `:338` (`missing_flag_headers`); `core/workflow.py:78-80` (`_flag_classes_unresolved`). Reaches all 8 CGT call sites: `hctp:319,328` · `potency:310,319` · `comparability:306,315` · `donor:302,311` · `durability:301,310` · `rmat:267` · `vector:284` · `lotrelease:276`.

Header-occurrence selection is **last-wins** (`matches[-1]`). A reviewer critique that contains a genuine findings block **followed later** by a filled clean footer — e.g. quoting the draft, or restating the example footer — has its real findings and its real veto silently replaced by the trailing copy.

**Reproduced live against this tree** (not the subagent's run; re-run independently):

```
WITHOUT trailing echo  flags: [['Cells are expanded ex vivo, …'], [], []]
WITHOUT trailing echo  veto : 'This is a 351 biologic; do not assert the 361 tier.'
WITH    trailing echo  flags: [[], [], []]
WITH    trailing echo  veto : None
missing_flag_headers WITH echo: []      <- the D-A11-1 fallback guard is defeated
```

With `review.approved` True, the workflow then reports `converged=True`, no veto banner, an empty flag section — a clean determination handed to the RA / QA approver while the reviewer actually halted it.

`missing_flag_headers` does not save it: an anchor match **anywhere** in the critique counts the class as "assessed", including inside the quoted block. Two triggers, one root class: (a) a caller plants the block in a Request field and it survives to the critique — `sanitize_for_prompt` preserves `\n` (`_internal.py:176`), so multi-line caller text reaches the executor prompt intact (the two model hops are plausible but unverified); (b) **no attacker at all** — the reviewer restates a clean footer on its own.

**Why the 1857-test suite is blind to it:** G1–G6 compare code-to-code and code-to-prompt. This defect lives in *runtime critique text*, which no guard recomputes.

**Suggested fix (do not apply unattended):** replace occurrence-*selection* with occurrence-*detection* — multiple line-anchored occurrences of a header whose contents differ ⇒ treat the class as **unresolved** and the veto as **present-but-ambiguous**, rather than picking one. Note that A11-M4 deliberately chose last-wins to defeat an *earlier* echo shadowing a real veto; first-wins simply inverts the exposure. Add the duplicate-block case to `tests/unit/test_parser_hardening.py` in the same change (D-A11-2).

**Not auto-applied:** CRITICAL; `core/_internal.py`; changes veto and convergence behaviour for all 30 veto workflows.

### HIGH

#### H-1 — Silent suppression of the veto-relevant Request fields at the 6000-char post-concat cap

> **STATUS: FIXED** (2026-07-25, after this report was filed) — the per-call-site `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)` guillotine is replaced across all 67 domain workflows by one shared `sanitize_request_text(request)` (`core/_internal.py`): control-char / NFC pass only, plus a `_MAX_REQUEST_PROMPT_CHARS = 60_000` field-count backstop (the per-field 1500 caps stay the real bound; largest `to_prompt_text` today is 10 fields ~15k, >4x headroom). Locked as **D-A11-6**. Guarded at author time by **G7** in `tests/unit/test_workflow_conventions.py` (no workflow may call `.to_prompt_text()` directly — the helper is the sole caller) and behaviourally by `tests/unit/test_hctp_classification.py::TestH1FullRequestReachesExecutor` (9x1.5k request, trailing field must reach the round-1 executor prompt) + `tests/unit/test_internal.py::TestSanitizeRequestText`. Independent reviewer verdict SHIP-WITH-FOLDIN; 2 stale-comment fold-ins closed pre-commit. **DEFERRED (not part of this fix):** the per-field visible truncation marker the suggestion below also proposed is **L-IND-5** (per-field silent `[:cap]`), a distinct and smaller-blast-radius class — every field is still represented after D-A11-6 — kept as a documented known gap (D-DEPTH-3). The original finding is preserved below unedited.

`hctp:276` · `potency:267` · `comparability:263` · `donor:259` · `durability:258` · `rmat:227` · `vector:244` · `lotrelease:236`, via `core/_internal.py:216-221`.

Per-field cap 1500 × 7–9 fields = 10.7k–13.8k chars, then one hard cut to 6000 with a single generic `...[truncated]` marker at the very end. **Reproduced live on `hctp_classification`:**

```
raw=13759  capped=6000  fields=9  kept=4
dropped: Intended use / homology · Combination with another article ·
         Systemic effect / metabolic dependence · Proposed regulatory tier ·
         Precedent determinations
```

The dropped tail is precisely what the flag classes and the veto gate exist to test — 1271.10(a) prongs 2/3/4 for HCT/P; urgent-medical-need documentation for donor eligibility; oncogenicity data for vector safety. And the **reviewer never sees the request** (`reviewer.review(output, criteria=…)` takes the executor draft only), so evidence dropped from the executor prompt is dropped from the whole adversarial loop.

Not adversarial-only: 6000 ÷ 9 ≈ 666 chars/field, which realistic CMC narratives exceed routinely. A caller can also weaponise it by padding an early field.

**Suggested fix:** budget the cap per field rather than post-concat (e.g. `6000 // len(fields)`), or raise the concat cap above `n_fields × _MAX_FIELD_CHARS`, and emit a per-field truncation marker so the drop is visible in the output. Same convention across all 71 workflows — fix the convention, not the 8 instances.

**Not auto-applied:** HIGH; changes what reaches both models; convention-level across the repo.

### MEDIUM

#### M-1 — Flag headers line-anchored inside the reviewer-criteria prose

`cgt_potency_assay.py:88` · `cgt_comparability.py:94` · `cgt_durability_claim.py:81,91` · `rmat_designation.py:74` · `vector_safety.py:73,79` · `cgt_lot_release_spec.py:89` · `skills/templates/lotrelease_review.md:34`.

Line-wrapping puts a bare `<HEADER> FLAGS:.` at line start inside the criteria text, where `_header_anchor_re`'s indent-tolerant prefix matches it. If the reviewer restates the rubric after its footer, the real findings are replaced by the template placeholder (`['[bullet list, or "None detected"]']`) and, in the veto modules, `extract_veto_directive` returns the literal `<verbatim directive, or "None">` — the halt fires with its reason destroyed. A partial quote instead yields phantom flags (`cgt_lot_release_spec` → `SHELF-LIFE FLAGS: ['ready for QC sign-off. Otherwise: requires revision.']`).

Fail-closed on the convergence gate; the damage is to finding integrity and to the approver checklist. Same root class as C-1.

**Suggested fix:** re-wrap so no header sits at line start outside the emission block (e.g. `… Flag under\n   MOA-LINKAGE FLAGS:.` → keep the header on the prior line). **Not auto-applied:** MEDIUM, and editing reviewer-criteria prose is a prompt change, i.e. a behaviour change.

#### M-2 — Cross-run / cross-case wiki bleed into the executor prompt

`core/wiki.py:235-240` filters `context_for_round` on `round_num` only — no run, case, or workflow scoping. All 8 examples point the wiki at one persistent file (`examples/lifesciences/donor_eligibility.py:76-77`), so a second run reads the previous case's reviewer critiques into the current case's executor prompt. For `donor_eligibility` that means donor A's PHI-bearing narrative reaching donor B's determination prompt. Content is fenced and sanitized (data-not-instructions), but it is the wrong donor's data.

**Suggested fix:** scope wiki entries by run/case id, or give each example a per-run workspace. **Not auto-applied:** MEDIUM; `core/wiki.py`.

#### M-3 — Predictable `/tmp` workspace in all 8 examples

`examples/lifesciences/donor_eligibility.py:39` (`/tmp/donor-eligibility-example`) + 7 siblings; `core/config.py:220-221`. On a shared POSIX host, an attacker who pre-creates the directory as a symlink wins — `mkdir(exist_ok=True)` succeeds and `safe_resolve_path` resolves *through* the symlink, so the `must_be_under` check compares against the resolved target and passes. `ledger.json` / `wiki.json` (donor narrative + every critique) land in the attacker's directory. Files themselves are 0600 via `mkstemp`; the directory is the hole.

MEDIUM for `donor_eligibility` (PHI), LOW for the other seven. Examples are marked NOT FOR PRODUCTION.

**Suggested fix:** `tempfile.mkdtemp()` per run, or `O_NOFOLLOW`-style directory validation in `Config`. **Not auto-applied:** MEDIUM + touches `core/config.py`.

### LOW

| # | Finding | File:line | Suggested fix | Why not auto-applied |
|---|---|---|---|---|
| L-1 | No static guard that the convergence gate uses `_flag_classes_unresolved` — D-A11-1 is a documented invariant with no recomputing check (G1–G6 cover its neighbours). All 8 comply today. | `tests/unit/test_workflow_conventions.py` | Add G8: assert no workflow module's gate uses a bare `not any(...)` over flag values (G7 is now taken by the H-1 request-text guard, D-A11-6) | New shared-conventions guard, not confined to one module; outside the auto-fix categories |
| L-2 | `accumulated[header].extend(...)` never resets — ~4.8 MB worst case in `WorkflowResult.metadata` at 50 rounds. Never re-injected into a prompt; metadata dedups. | `hctp:320` +7 | Cap accumulation, or dedup on write | Behaviour change |
| L-3 | Prompt states `Score >= 7.5`, code enforces `config.score_threshold` (8.0). Fail-closed. Domain-wide: all 14 no-veto lifesciences modules. | `rmat:86` · `vector:95` · `lotrelease:88`; `core/agents.py:290-293` | Interpolate the configured threshold into the criteria, or align the literal — across all 14 | Prompt text = behaviour; convention-level across the domain, not a CGT defect |
| L-4 | Only flag class #1 carries an `== [expected]` assertion in each of the 8 test files; classes 2–3 unguarded against parser slurp. No test covers a missing header, a duplicate header block (C-1), or the 6000-char drop (H-1). | `test_hctp_classification.py:166,190` +7 | Add equality assertions for classes 2–3 and regression tests for C-1/H-1 | Adding new assertions is not in the auto-fix set; the C-1/H-1 tests must land with their fixes |
| L-5 | Vetoed draft rendered in full into `.output` with no PHI caveat line (comment added — see Fixed §2 — but the output text itself is unchanged). | `donor_eligibility.py:388-395` | Add a PHI-handling line to the donor output composition | Changes `WorkflowResult.output`; would need test updates |
| L-6 | Ledger writes silently swallowed when `config.max_claim_text_chars > 2000` — `ClaimLedger` is constructed without `max_claim_chars`, `add` raises, and `workflow.py:117-118` discards it. Empty audit trail, no warning. | `core/workflow.py:113-118`; `core/ledger.py:25,113` | Pass `max_claim_chars` through, or warn on the swallow | Shared spine |
| L-7 | No non-empty validation on any of the 8 `*Request` dataclasses — all-empty input still yields a disclaimer-stamped 361 classification or donor-eligibility determination. | `hctp:205-248` +7 | `__post_init__` requiring the decision-critical fields | Behaviour change; convention-level across 71 workflows |
| L-8 | `request` accepted and never read by all 8 checklist builders. Harmless today (it is why no unsanitized caller text reaches the checklist) but dead surface inviting a future raw interpolation. | `hctp:415-419` +7 | Drop the parameter, or comment the intent | Signature change |

---

## Gate

```
python -m ruff check .      → All checks passed!
python -m mypy src          → Success: no issues found in 120 source files
python -m pytest tests/unit → 1857 passed in 103.04s
```

Green before the fixes and after. No fix was reverted; every applied change held on the first gate run. Working tree clean at `e1d9f71`. **Nothing pushed.**

---

## Recommended order for the morning

1. **C-1** — spine parser. One fix, all 30 veto workflows inherit it. Land with a `test_parser_hardening.py` case (D-A11-2).
2. **H-1** — per-field cap budgeting. Convention-level; fixing it per-module would be the third instance of the compounding pattern already logged twice (M-PC-1, H-IND-1).
3. **M-1** — criteria re-wrap; cheap, 8 lines, but it is a prompt change so it wants a deliberate review.
4. **L-1** — the G7 guard. Retires the D-A11-1 bug class at author time; that is the durable win, not the per-instance check.

M-2 / M-3 are example-and-spine hygiene, safe to batch later. L-2…L-8 are backlog.
