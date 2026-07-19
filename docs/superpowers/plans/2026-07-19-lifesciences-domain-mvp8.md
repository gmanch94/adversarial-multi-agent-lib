# Lifesciences Domain MVP-8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a 7th domain — `lifesciences` — as 8 MVP workflows (5 reviewer-veto, 3 advisory) modelling a diversified medical-products manufacturer's regulatory-affairs / quality desk, following the locked no-base-class recipe.

**Architecture:** Each workflow is a self-contained module under `src/adv_multi_agent/lifesciences/workflows/`, structurally cloned from one of two proven on-disk healthcare skeletons, with domain-specific review criteria / flag classes / prompts / checklist / disclaimer written fresh. No domain base class (D-RETAIL-7 → D-IND-1 → D-HEALTH-1 → **D-LIFESCI-1**). All flag parsing delegates to the shared `core/_internal.py` helpers, so the domain inherits M1 / H-IND-1 / L-PC-5 hardening automatically.

**Tech Stack:** Python 3.11+, `dataclasses`, `pytest` + `pytest-asyncio`, the repo's `BaseWorkflow` / `ExecutorAgent` / `ReviewerAgent` / `ClaimLedger` / `ResearchWiki` infra. No new dependencies.

---

## Skeleton-vs-prose rule (read before every task)

**Skeleton = a real on-disk file you copy structurally. Prose = you write in full.** That is the whole discriminator for this plan.

- The two skeletons already exist, are stable, and are the reference for the mechanical run-loop, veto handling, flag-section shape, and metadata assembly. **Do not inline copies of the run-loop into this plan or invent a new one — open the file and clone its structure:**
  - **No-veto skeleton:** `src/adv_multi_agent/healthcare/workflows/diagnosis_code_audit.py` — dict-driven `_FLAG_HEADERS` tuple + `current` / `accumulated` dicts + `_format_flag_section(current)` + `_build_*_checklist(request, accumulated)`. Gate: `review.approved and not any(current.values())`.
  - **Veto skeleton:** `src/adv_multi_agent/healthcare/workflows/adverse_event_triage.py` — named per-class flag lists + `_extract_veto` (delegates to `extract_veto_directive`) + `_compose_output` + `_VETO_BANNER` + `first_draft` in metadata. Audit-trail write happens BEFORE the veto check. Gate: `review.approved and not <flag1> and not <flag2> and not <flag3>` (veto breaks first).

- **What you must write in full per workflow (the actual work — never abbreviate as "like the assay one"):** the weighted 5-dimension review-criteria block, the veto-criteria block + FORMAT NOTE (veto workflows), the initial/revision prompt section structure, the `_format_flag_section` banner text per flag class, the `_build_*_checklist` owner + items, the `_DISCLAIMER` wording, the example scenario, and the test critiques with **exact `== [...]` assertions**. The spec gives fields + one-line flag-class hints + gate + veto trigger + approver + gaps; it does **not** give criteria bodies, prompts, checklists, or tests. Those are this plan's job and are written out below.

## Idiom pins (prevent drift across the 8)

- **3 no-veto workflows (#7, #8, #6): use the dict-driven idiom** (`diagnosis_code_audit.py` shape) — `_FLAG_HEADERS` tuple, `current`/`accumulated` dicts, `not any(current.values())` gate.
- **5 veto workflows (#2, #1, #3, #4, #5): use the named-list idiom** (`adverse_event_triage.py` shape) — `current_<class>_flags` / `all_<class>_flags` named lists, `_extract_veto`, `_compose_output`, `first_draft`.
- Do not mix the two styles within one archetype.

## No-brand-names constraint (D-LIFESCI-3 — load-bearing)

**No brand or company name appears in any lifesciences artifact — code, prompt template, example, or test.** Scenarios use generic product **categories** only (e.g. "a rapid antigen test", "a continuous glucose monitor", "a drug-eluting stent", "an adult nutritional shake", "an infusion pump"). Illustrative FDA citations (21 CFR parts) are scenario context, not legal advice.

Task 0 adds an automated tripwire (`tests/unit/test_lifesciences_no_brand_names.py`). **Autonomy decision (surfaced per `~/.claude/rules/autonomy.md`):** the tripwire's denylist seed is stored **base64-encoded** and decoded at runtime, specifically so the literal company/brand strings never appear in plaintext anywhere in the repo — honoring D-LIFESCI-3 "don't name it anywhere" while still failing loudly if a brand string is introduced into the domain tree. Rationale: security/durability path — the guard is a durable tripwire for the known case (matches the CI-as-enforcement rule); it cannot prove absence of *all* possible brands, so it **pairs with** the ship-audit review in Task 9, it does not replace it. Honoring the user's explicit hard constraint outranks the advisor's convenience suggestion to store the seed in plaintext.

---

## File structure

```
src/adv_multi_agent/lifesciences/
  __init__.py                                   # domain docstring + advisory banner
  workflows/
    __init__.py                                 # one-line docstring
    design_control_traceability.py              # #7 no-veto
    nutrition_health_claim.py                   # #8 no-veto
    combination_product_pmoa.py                 # #6 no-veto
    assay_performance_claim.py                  # #2 veto
    substantial_equivalence_510k.py             # #1 veto
    promotional_off_label_review.py             # #3 veto
    device_reportability.py                     # #4 veto (boundary vs healthcare)
    field_action_classification.py              # #5 veto (boundary vs industrial)
  skills/
    __init__.py
    templates/                                  # 4 templates/workflow = 32 files
examples/lifesciences/
  __init__.py
  <one runnable synthetic example per workflow> # 8 files
tests/unit/
  test_<workflow>.py                            # 8 files
  test_lifesciences_no_brand_names.py           # brand tripwire (Task 0)
```

Wiring touched once (Task 0): `pyproject.toml` package-data row; `core/skills/mcp_server.py` `_ALLOWED_DOMAINS`; `core/skills/registry.py` `_KNOWN_DOMAINS` (+ two docstring mentions); `docs/decisions.md` rows D-LIFESCI-1..4.

## Template-prefix map (skill templates + reused across tasks)

| # | Module | Request class | Template prefix | Idiom |
|---|--------|---------------|-----------------|-------|
| 7 | `design_control_traceability` | `DesignControlRequest` | `design_` | no-veto |
| 8 | `nutrition_health_claim` | `NutritionClaimRequest` | `nutrition_` | no-veto |
| 6 | `combination_product_pmoa` | `PMOARequest` | `pmoa_` | no-veto |
| 2 | `assay_performance_claim` | `AssayClaimRequest` | `assay_` | veto |
| 1 | `substantial_equivalence_510k` | `SERequest` | `se510k_` | veto |
| 3 | `promotional_off_label_review` | `PromoReviewRequest` | `promo_` | veto |
| 4 | `device_reportability` | `ReportabilityRequest` | `reportability_` | veto |
| 5 | `field_action_classification` | `FieldActionRequest` | `fieldaction_` | veto |

---

## Task 0: Package scaffolding + wiring + brand tripwire

Wiring first so imports resolve as each workflow lands.

**Files:**
- Create: `src/adv_multi_agent/lifesciences/__init__.py`
- Create: `src/adv_multi_agent/lifesciences/workflows/__init__.py`
- Create: `src/adv_multi_agent/lifesciences/skills/__init__.py`
- Create: `examples/lifesciences/__init__.py`
- Modify: `pyproject.toml:67` (add package-data row after healthcare)
- Modify: `src/adv_multi_agent/core/skills/mcp_server.py:56` (`_ALLOWED_DOMAINS`)
- Modify: `src/adv_multi_agent/core/skills/registry.py:337` (`_KNOWN_DOMAINS`) + `:346` docstring
- Modify: `docs/decisions.md` (append D-LIFESCI-1..4)
- Create: `tests/unit/test_lifesciences_no_brand_names.py`

- [ ] **Step 1: Create the four `__init__.py` files**

`src/adv_multi_agent/lifesciences/__init__.py`:
```python
"""Lifesciences domain — adversarial multi-agent regulatory decision support.

See docs/superpowers/specs/2026-07-19-lifesciences-domain-design.md for the
27-workflow catalog. MVP-8 is shipped; 19 Phase-2 workflows are designed but
not built.

Domain = regulated medical-product MANUFACTURER decisions (RA / QA / MLR /
post-market surveillance) — distinct from the provider-facing `healthcare`
domain and the general-manufacturing `industrial` domain (D-LIFESCI-2).

ALL OUTPUT IS ADVISORY DECISION-SUPPORT. NO WORKFLOW IS A REGULATORY
SUBMISSION, AND NONE REPLACES QUALIFIED RA/QA SIGN-OFF. NOT LEGAL OR MEDICAL
ADVICE. No brand or company names appear anywhere in this domain (D-LIFESCI-3).
"""
```

`src/adv_multi_agent/lifesciences/workflows/__init__.py`:
```python
"""Lifesciences workflows — MVP-8 per D-LIFESCI-1."""
```

`src/adv_multi_agent/lifesciences/skills/__init__.py`:
```python
"""Lifesciences bundled skill templates."""
```

`examples/lifesciences/__init__.py`:
```python
"""Runnable synthetic examples for lifesciences workflows. Require live API keys."""
```

- [ ] **Step 2: Add the pyproject package-data row**

In `pyproject.toml`, immediately after the healthcare line (`:67`):
```toml
"adv_multi_agent.healthcare.skills" = ["templates/*.md"]
"adv_multi_agent.lifesciences.skills" = ["templates/*.md"]
```

- [ ] **Step 3: Register the domain in the two allowlists**

`core/skills/mcp_server.py` — extend the frozenset:
```python
_ALLOWED_DOMAINS = frozenset({"research", "parole", "retail", "pc", "industrial", "healthcare", "lifesciences"})
```

`core/skills/registry.py` — extend `_KNOWN_DOMAINS`:
```python
    _KNOWN_DOMAINS: frozenset[str] = frozenset(
        {"research", "parole", "retail", "pc", "industrial", "healthcare", "lifesciences"}
    )
```
and in the `bundled_skills_path` docstring (`:346`) change the enumerated list to include `` ``"healthcare"``, or ``"lifesciences"`` ``.

- [ ] **Step 4: Append decision rows to `docs/decisions.md`**

Append (verbatim from the spec's D-LIFESCI-1..4 table — copy the four rows). Keep the append-only format used by existing rows. Include the base64-seed autonomy decision as a one-line note under D-LIFESCI-3.

- [ ] **Step 5: Write the brand tripwire test**

`tests/unit/test_lifesciences_no_brand_names.py`:
```python
"""D-LIFESCI-3 tripwire: no brand/company name in any lifesciences artifact.

The denylist seed is base64-encoded ON PURPOSE so the literal company/brand
strings never appear in plaintext anywhere in this repository (that is the
whole point of D-LIFESCI-3). Decoded only at runtime for the scan. This is a
tripwire for the KNOWN archetype case — it cannot prove the absence of every
possible brand, so it complements, not replaces, the ship-audit review.
"""
from __future__ import annotations

import base64
from pathlib import Path

import pytest

# base64 of the archetype company name + its DISTINCTIVE flagship product brands,
# lowercased. Decoded at runtime only. Add new seeds as base64 to keep plaintext
# clean. RULE: only seed distinctive tokens — the scan is a case-insensitive
# SUBSTRING match, so a brand that is also a common word (e.g. a nutrition brand
# spelled like the verb "ensure") is deliberately EXCLUDED to avoid false
# positives on ordinary regulatory prose. Distinctive tokens only.
_ENCODED_DENYLIST: tuple[str, ...] = (
    "YWJib3R0",          # <company>
    "YmluYXhub3c=",      # <rapid-test brand>
    "c2ltaWxhYw==",      # <infant-formula brand>
    "cGVkaWFzdXJl",      # <pediatric-nutrition brand>
    "YWxpbml0eQ==",      # <core-lab brand>
    "bWl0cmFjbGlw",      # <structural-heart brand>
)

_DENYLIST = tuple(base64.b64decode(s).decode("ascii").lower() for s in _ENCODED_DENYLIST)

_REPO_ROOT = Path(__file__).resolve().parents[2]
_SCAN_ROOTS = (
    _REPO_ROOT / "src" / "adv_multi_agent" / "lifesciences",
    _REPO_ROOT / "examples" / "lifesciences",
)
_SCAN_TESTS_GLOB = "test_*.py"  # lifesciences workflow tests in tests/unit


def _lifesciences_files() -> list[Path]:
    files: list[Path] = []
    for root in _SCAN_ROOTS:
        if root.exists():
            files.extend(p for p in root.rglob("*") if p.suffix in {".py", ".md"})
    tests_dir = _REPO_ROOT / "tests" / "unit"
    lifesci_modules = {
        "test_design_control_traceability.py",
        "test_nutrition_health_claim.py",
        "test_combination_product_pmoa.py",
        "test_assay_performance_claim.py",
        "test_substantial_equivalence_510k.py",
        "test_promotional_off_label_review.py",
        "test_device_reportability.py",
        "test_field_action_classification.py",
    }
    files.extend(tests_dir / name for name in lifesci_modules if (tests_dir / name).exists())
    return files


def test_denylist_decodes_nonempty() -> None:
    # Guards against a corrupted seed silently disabling the tripwire.
    assert _DENYLIST
    assert all(term for term in _DENYLIST)


@pytest.mark.parametrize("path", _lifesciences_files(), ids=lambda p: p.name)
def test_no_brand_name_in_file(path: Path) -> None:
    text = path.read_text(encoding="utf-8").lower()
    hits = [term for term in _DENYLIST if term in text]
    assert not hits, (
        f"{path.relative_to(_REPO_ROOT)} contains brand/company name(s) "
        f"(D-LIFESCI-3 violation). Use a generic product CATEGORY instead."
    )
```
> **Note to implementer:** this test file itself is excluded from its own scan (it's not in `lifesci_modules`), so the encoded seeds don't self-trip. If `_lifesciences_files()` returns empty at Task-0 time, `test_no_brand_name_in_file` is a no-op parametrize — that's fine; it arms as workflow files land. `test_denylist_decodes_nonempty` always runs.

- [ ] **Step 6: Run the wiring checks**

Run: `python -c "import adv_multi_agent.lifesciences; from adv_multi_agent.core.skills.registry import SkillRegistry; print(SkillRegistry.bundled_skills_path('lifesciences'))"`
Expected: prints a path ending in `lifesciences\skills\templates` (no `ValueError`).

Run: `pytest tests/unit/test_lifesciences_no_brand_names.py -v`
Expected: `test_denylist_decodes_nonempty` PASS; `test_no_brand_name_in_file` collects 0 or more, all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/adv_multi_agent/lifesciences examples/lifesciences pyproject.toml src/adv_multi_agent/core/skills/mcp_server.py src/adv_multi_agent/core/skills/registry.py docs/decisions.md tests/unit/test_lifesciences_no_brand_names.py
git commit -m "feat(lifesciences): scaffold 7th domain package, wiring, and D-LIFESCI-3 brand tripwire"
```

---

## Task 1: `DesignControlTraceabilityWorkflow` (#7, no-veto) — Devices

**Skeleton:** clone `src/adv_multi_agent/healthcare/workflows/diagnosis_code_audit.py` (dict-driven, no-veto). Gate uses `not any(current.values())`.

**Files:**
- Create: `src/adv_multi_agent/lifesciences/workflows/design_control_traceability.py`
- Test: `tests/unit/test_design_control_traceability.py`
- Create: `examples/lifesciences/design_control_traceability.py`
- Create: `src/adv_multi_agent/lifesciences/skills/templates/design_{initial,revision,review,checklist}.md`

- [ ] **Step 1: Write the module — constants**

Module docstring: ARIS cite (arXiv:2605.03042) + `⚠️ NOT FOR PRODUCTION DEPLOYMENT.` + `PRODUCTION_GAPS:` naming PLM (Windchill / Teamcenter), requirements management (DOORS), eQMS, ISO 14971 risk-management file — as caller-pasted text today, not live integrations; a qualified Design Assurance / QE approver required; output never auto-filed.

```python
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated design-control traceability audit is "
    "decision-support, not a Design History File and not a regulatory "
    "submission. A qualified Design Assurance engineer or QE must independently "
    "verify every input-output-verification-validation link against the DHF "
    "before any 21 CFR 820.30 / ISO 13485 conclusion. Not legal or medical advice."
)

_FLAG_HEADERS: tuple[str, ...] = (
    "TRACE-GAP FLAGS:",
    "VERIFICATION FLAGS:",
    "VALIDATION FLAGS:",
)
```

- [ ] **Step 2: Write the review criteria (full)**

```python
_DESIGN_CONTROL_REVIEW_CRITERIA = """\
Evaluate this design-control traceability audit on five dimensions. Score each 0–10.

1. INPUT-OUTPUT TRACEABILITY (30%) — CRITICAL
   Does every design input (requirement) trace to at least one design output
   (specification), and every output trace back to an input? Penalise orphan
   inputs and orphan outputs. Flag each broken link under TRACE-GAP FLAGS:.

2. VERIFICATION EVIDENCE (25%) — CRITICAL
   Does every design output have verification evidence demonstrating the output
   meets the input? Penalise outputs asserted verified without cited evidence.
   Flag gaps under VERIFICATION FLAGS:.

3. VALIDATION EVIDENCE (20%) — CRITICAL
   Does every user need have design-validation evidence (device meets user
   needs / intended use)? Penalise V&V conflation (verification cited where
   validation is required). Flag gaps under VALIDATION FLAGS:.

4. RISK-CONTROL LINKAGE (15%)
   Are ISO 14971 risk controls traced to the verification/validation that
   confirms their effectiveness? Penalise risk controls with no confirming V&V.

5. ACTIONABILITY (10%)
   Is each gap specific enough for a QE to close (which input, which output,
   what evidence is missing)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero TRACE-GAP FLAGS AND zero VERIFICATION FLAGS AND zero
VALIDATION FLAGS: ready for Design Assurance sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  TRACE-GAP FLAGS: [bullet list, or "None detected"]
  VERIFICATION FLAGS: [bullet list, or "None detected"]
  VALIDATION FLAGS: [bullet list, or "None detected"]
"""
```

- [ ] **Step 3: Write the initial + revision prompts**

Clone the `diagnosis_code_audit.py` prompt shell (same `{request_text}` / `{wiki_context}` / `{flag_section}` placeholders). Initial-prompt section list:
```
## Traceability matrix summary
## Verification coverage
## Validation coverage
## Risk-control linkage
## Gaps and recommendations
## Claims
```
Revision prompt: mirror the skeleton; the flagged-item instruction is *"For any flagged item: cite the exact missing input↔output↔evidence link from the DHF inputs; do not assert a link that is not in the supplied evidence."*

- [ ] **Step 4: Write the Request dataclass**

```python
@dataclass
class DesignControlRequest:
    device_description: str
    design_inputs: str
    design_outputs: str
    verification_evidence: str
    validation_evidence: str
    risk_analysis_reference: str
    design_review_records: str
    trace_matrix_summary: str

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Device description: {self.device_description[:cap]}",
            f"Design inputs: {self.design_inputs[:cap]}",
            f"Design outputs: {self.design_outputs[:cap]}",
            f"Verification evidence: {self.verification_evidence[:cap]}",
            f"Validation evidence: {self.validation_evidence[:cap]}",
            f"Risk analysis reference: {self.risk_analysis_reference[:cap]}",
            f"Design review records: {self.design_review_records[:cap]}",
            f"Trace matrix summary: {self.trace_matrix_summary[:cap]}",
        ])
```
Give each field a one-line docstring (mirror the skeleton style).

- [ ] **Step 5: Write the workflow class**

Clone the `DiagnosisCodeAuditWorkflow.run` loop exactly (dict-driven `current`/`accumulated`, `not any(current.values())` gate, output suffixed with `_DISCLAIMER`). `_format_flag_section` banners:
```python
banner = {
    "TRACE-GAP FLAGS:": (
        "⚠️  TRACE-GAP FLAGS (name the orphan input or output; do not assert a "
        "link absent from the supplied DHF evidence):"
    ),
    "VERIFICATION FLAGS:": (
        "⚠️  VERIFICATION FLAGS (cite the missing verification evidence for the "
        "named design output):"
    ),
    "VALIDATION FLAGS:": (
        "⚠️  VALIDATION FLAGS (cite the missing design-validation evidence for the "
        "named user need; do not substitute verification for validation):"
    ),
}
```
`_build_design_control_checklist` — first line `"[OWNER: Design Assurance / Quality Engineering]"`, then per-flag-class conditional lines, then:
```
[ ] Close every trace gap against the DHF before design transfer
[ ] Confirm V&V evidence resolves to controlled records (not draft)
[ ] Update the ISO 14971 risk-management file for any control lacking confirming V&V
[ ] Obtain Design Assurance sign-off before design freeze
```
Metadata id field: `"device_description"` (sanitized, 200 chars). Flag metadata keys: `trace_gap_flags`, `verification_flags`, `validation_flags`, plus `design_control_checklist`, `disclaimer`, `ledger_summary`.

- [ ] **Step 6: Write the tests (exact assertions)**

`tests/unit/test_design_control_traceability.py` — mirror `test_adverse_event_triage.py` structure minus the veto class, plus `TestScoreThresholdBoundary`. Config `score_threshold=7.5`.

Key exact-assertion cases (F2 lesson — no `any(...)` on flag lists):
```python
async def test_does_not_converge_when_trace_gap_flags_present(self, tmp_path):
    critique = (
        "Overall score: 7.0/10\n"
        "Key issues: orphan input\n"
        "TRACE-GAP FLAGS:\n- Design input DI-04 has no linked design output\n"
        "VERIFICATION FLAGS: None detected\n"
        "VALIDATION FLAGS: None detected\n"
    )
    # max_review_rounds=1
    result = await wf.run(request=make_request())
    assert result.converged is False
    assert result.metadata["trace_gap_flags"] == ["Design input DI-04 has no linked design output"]

async def test_stops_at_sibling_header(self, tmp_path):
    # A trailing uppercase WORD: section must NOT be slurped into trace_gap_flags.
    critique = (
        "Overall score: 7.0/10\n"
        "TRACE-GAP FLAGS:\n- Orphan output DO-11\n"
        "VERIFICATION FLAGS: None detected\n"
        "VALIDATION FLAGS: None detected\n"
        "RECOMMENDATION: schedule a design review\n"
    )
    result = await wf.run(request=make_request())
    assert result.metadata["trace_gap_flags"] == ["Orphan output DO-11"]
```
Plus: `TestRequestToPromptText` (all 8 fields present; per-field cap), `test_converges_clean` (`assert result.converged is True`), `TestMetadata` (all keys + `checklist[0] == "[OWNER: Design Assurance / Quality Engineering]"`), `TestDisclaimer`, `TestScoreThresholdBoundary` (zero flags but `approved=False` @ 7.4 across 3 rounds → `converged is False`, `rounds == 3`).

- [ ] **Step 7: Run the tests**

Run: `pytest tests/unit/test_design_control_traceability.py -v`
Expected: all PASS.

- [ ] **Step 8: Write the example**

`examples/lifesciences/design_control_traceability.py` — clone the `examples/healthcare/adverse_event_triage.py` shell (imports, `Config` with `ReviewerProvider.OPENAI`, print block). Scenario: **a continuous glucose monitor** (generic category — NO brand). Populate `DesignControlRequest` with a realistic DHF excerpt containing one deliberate orphan input so the reviewer would flag TRACE-GAP. `workspace_dir="/tmp/design-control-example"`.

- [ ] **Step 9: Write the 4 skill templates**

Under `src/adv_multi_agent/lifesciences/skills/templates/`, mirroring `healthcare/skills/templates/adverse_review.md` frontmatter shape (`name` / `description` / `inputs`):
- `design_initial.md` — frontmatter (`inputs: [request_text, wiki_context]`) + the `_INITIAL_PROMPT` body from Step 3.
- `design_revision.md` — (`inputs: [previous, score, critique, suggestions, flag_section, wiki_context]`) + `_REVISION_PROMPT` body.
- `design_review.md` — (`inputs: [output]`) + the `_DESIGN_CONTROL_REVIEW_CRITERIA` body + `REVIEW:\n{output}` tail (as the healthcare example does).
- `design_checklist.md` — (`inputs: [flags]`) + the checklist items from Step 5 as a static markdown list.

The bodies are the constants already defined in Steps 2–5 — extract, don't rewrite.

- [ ] **Step 10: Commit**

```bash
git add src/adv_multi_agent/lifesciences/workflows/design_control_traceability.py tests/unit/test_design_control_traceability.py examples/lifesciences/design_control_traceability.py src/adv_multi_agent/lifesciences/skills/templates/design_*.md
git commit -m "feat(lifesciences): add DesignControlTraceabilityWorkflow (no-veto, 21 CFR 820.30 traceability)"
```

---

## Task 2: `NutritionHealthClaimWorkflow` (#8, no-veto) — Nutrition

**Skeleton:** clone `diagnosis_code_audit.py` (dict-driven, no-veto). Gate `not any(current.values())`.

**Files:**
- Create: `src/adv_multi_agent/lifesciences/workflows/nutrition_health_claim.py`
- Test: `tests/unit/test_nutrition_health_claim.py`
- Create: `examples/lifesciences/nutrition_health_claim.py`
- Create: `.../skills/templates/nutrition_{initial,revision,review,checklist}.md`

- [ ] **Step 1: Constants**

Docstring PRODUCTION_GAPS: substantiation-dossier repository, structure-function-claim notification log, nutrient database, allergen-control plan.
```python
_MAX_FIELD_CHARS = 1500
_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated nutrition label-claim review is "
    "decision-support, not a regulatory filing or a substantiation decision. "
    "A qualified Nutrition Regulatory / Scientific Affairs reviewer must "
    "independently verify claim substantiation, nutrient adequacy, and allergen "
    "declarations before any label is released. Not legal or medical advice."
)
_FLAG_HEADERS = ("CLAIM-SUBSTANTIATION FLAGS:", "NUTRIENT-ADEQUACY FLAGS:", "ALLERGEN FLAGS:")
```

- [ ] **Step 2: Review criteria (full)**

```python
_NUTRITION_REVIEW_CRITERIA = """\
Evaluate this nutrition label-claim review on five dimensions. Score each 0–10.

1. CLAIM SUBSTANTIATION (30%) — CRITICAL
   Does every structure-function claim have competent-reliable scientific
   evidence in the substantiation dossier, and every disease (health) claim an
   authorization? Penalise a disease claim made as a structure-function claim
   without authorization. Flag gaps under CLAIM-SUBSTANTIATION FLAGS:.

2. NUTRIENT ADEQUACY (25%) — CRITICAL
   Is the nutrient profile adequate against the applicable requirement for the
   product category and target population (e.g. infant-formula nutrient
   minimums, 21 CFR 107)? Penalise a profile below a required minimum. Flag
   gaps under NUTRIENT-ADEQUACY FLAGS:.

3. ALLERGEN DECLARATION (20%) — CRITICAL
   Is every major allergen declared, and is a cross-contact statement present
   where the process warrants it? Penalise an undeclared major allergen. Flag
   gaps under ALLERGEN FLAGS:.

4. CLAIM-CATEGORY ROUTING (15%)
   Is each claim correctly categorised (structure-function vs nutrient-content
   vs health) and does the label meet that category's requirements? Penalise
   mis-categorised claims.

5. ACTIONABILITY (10%)
   Is each finding specific enough for a regulatory reviewer to resolve (which
   claim, which nutrient, which allergen)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero CLAIM-SUBSTANTIATION FLAGS AND zero NUTRIENT-ADEQUACY
FLAGS AND zero ALLERGEN FLAGS: ready for Nutrition Regulatory sign-off.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  CLAIM-SUBSTANTIATION FLAGS: [bullet list, or "None detected"]
  NUTRIENT-ADEQUACY FLAGS: [bullet list, or "None detected"]
  ALLERGEN FLAGS: [bullet list, or "None detected"]
"""
```

- [ ] **Step 3: Prompts** — clone shell. Initial sections:
```
## Claim inventory and categorisation
## Substantiation assessment
## Nutrient adequacy
## Allergen declaration
## Findings and recommendations
## Claims
```
Revision flagged-item instruction: *"For any flagged item: cite the specific dossier evidence / nutrient requirement / allergen source; do not assert substantiation absent from the supplied dossier summary."*

- [ ] **Step 4: Request dataclass**

Fields (with one-line docstrings): `product_category`, `claim_set`, `substantiation_dossier_summary`, `target_population`, `nutrient_profile`, `allergen_declaration`, `infant_formula_flag`. `to_prompt_text` caps each at `_MAX_FIELD_CHARS`.

- [ ] **Step 5: Workflow class** — clone dict-driven loop. Banners name: substantiation ("cite competent-reliable evidence or the required notification"), nutrient-adequacy ("cite the applicable minimum, e.g. 21 CFR 107 for infant formula"), allergen ("name the undeclared major allergen or missing cross-contact statement"). Checklist owner `"[OWNER: Nutrition Regulatory + Scientific Affairs]"`; items:
```
[ ] Verify each structure-function claim against the substantiation dossier
[ ] Confirm a disease/health claim has authorization before use
[ ] Confirm nutrient profile meets the applicable minimum for the population
[ ] Confirm all major allergens are declared and cross-contact stated
[ ] Obtain Nutrition Regulatory sign-off before label release
```
Metadata id field `"product_category"`; flag keys `claim_substantiation_flags`, `nutrient_adequacy_flags`, `allergen_flags`; `nutrition_checklist`, `disclaimer`, `ledger_summary`.

- [ ] **Step 6: Tests (exact)** — `score_threshold=7.5`. Include `test_does_not_converge_when_allergen_flags_present` with `assert result.metadata["allergen_flags"] == ["Undeclared major allergen: milk"]` and a `test_stops_at_sibling_header` case (trailing `RECOMMENDATION:` not slurped). Plus the standard `to_prompt_text` / clean-converge / metadata-keys / disclaimer / threshold-boundary cases.

- [ ] **Step 7: Run** — `pytest tests/unit/test_nutrition_health_claim.py -v` → PASS.

- [ ] **Step 8: Example** — scenario: **an adult nutritional shake** carrying a structure-function claim plus an **infant-formula** nutrient-adequacy angle (generic categories, NO brand). One deliberate undeclared allergen so ALLERGEN fires. `workspace_dir="/tmp/nutrition-claim-example"`.

- [ ] **Step 9: Skill templates** — `nutrition_{initial,revision,review,checklist}.md` from Steps 2–5.

- [ ] **Step 10: Commit**
```bash
git add src/adv_multi_agent/lifesciences/workflows/nutrition_health_claim.py tests/unit/test_nutrition_health_claim.py examples/lifesciences/nutrition_health_claim.py src/adv_multi_agent/lifesciences/skills/templates/nutrition_*.md
git commit -m "feat(lifesciences): add NutritionHealthClaimWorkflow (no-veto, substantiation + allergen)"
```

---

## Task 3: `CombinationProductPMOAWorkflow` (#6, no-veto) — Cross-segment

**Skeleton:** clone `diagnosis_code_audit.py` (dict-driven, no-veto).

**Files:**
- Create: `src/adv_multi_agent/lifesciences/workflows/combination_product_pmoa.py`
- Test: `tests/unit/test_combination_product_pmoa.py`
- Create: `examples/lifesciences/combination_product_pmoa.py`
- Create: `.../skills/templates/pmoa_{initial,revision,review,checklist}.md`

- [ ] **Step 1: Constants** — PRODUCTION_GAPS: 21 CFR 3 + Office of Combination Products RFD-precedent database, jurisdictional-determination archive.
```python
_MAX_FIELD_CHARS = 1500
_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated primary-mode-of-action analysis is "
    "decision-support, not a Request for Designation and not a jurisdictional "
    "determination. A qualified Regulatory Strategy lead must independently "
    "confirm the PMOA, lead center, and pathway under 21 CFR 3 before any "
    "submission. Not legal or medical advice."
)
_FLAG_HEADERS = ("PMOA FLAGS:", "LEAD-CENTER FLAGS:", "PATHWAY FLAGS:")
```

- [ ] **Step 2: Review criteria (full)**
```python
_PMOA_REVIEW_CRITERIA = """\
Evaluate this combination-product PMOA analysis on five dimensions. Score each 0–10.

1. PMOA DETERMINATION (30%) — CRITICAL
   Is the primary mode of action consistent with the described therapeutic
   mechanism and each constituent's contribution? Penalise a PMOA that does not
   follow from the mechanism (e.g. a drug PMOA where the device provides the
   primary therapeutic effect). Flag under PMOA FLAGS:.

2. LEAD-CENTER ASSIGNMENT (25%) — CRITICAL
   Does the proposed lead center (CDER / CBER / CDRH) follow from the PMOA?
   Penalise a center assignment inconsistent with the determined PMOA. Flag
   under LEAD-CENTER FLAGS:.

3. PATHWAY CONSISTENCY (20%) — CRITICAL
   Is the proposed submission pathway (NDA / BLA / PMA / 510(k)) consistent with
   the center and PMOA? Penalise a pathway that does not match. Flag under
   PATHWAY FLAGS:.

4. PRECEDENT ALIGNMENT (15%)
   Do cited precedent products / RFD determinations actually support the
   proposed routing? Penalise precedents that are not analogous.

5. ACTIONABILITY (10%)
   Is the recommendation specific enough for a regulatory strategist to act on
   (which center, which pathway, which precedent)? Penalise vague routing.

Overall score = weighted average.
Score >= 7.5 AND zero PMOA FLAGS AND zero LEAD-CENTER FLAGS AND zero PATHWAY
FLAGS: ready for Regulatory Strategy sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PMOA FLAGS: [bullet list, or "None detected"]
  LEAD-CENTER FLAGS: [bullet list, or "None detected"]
  PATHWAY FLAGS: [bullet list, or "None detected"]
"""
```

- [ ] **Step 3: Prompts** — Initial sections:
```
## Constituent-part analysis
## Primary mode of action
## Lead-center determination
## Submission pathway
## Precedent support
## Claims
```
Revision instruction: *"For any flagged item: re-derive the PMOA from the therapeutic mechanism and each constituent's contribution; do not assert a center/pathway that does not follow from the PMOA."*

- [ ] **Step 4: Request dataclass** — fields: `product_description`, `constituent_parts`, `therapeutic_effect_mechanism`, `each_constituent_contribution`, `proposed_pmoa`, `proposed_lead_center`, `precedent_products`.

- [ ] **Step 5: Workflow class** — dict-driven loop. Checklist owner `"[OWNER: Regulatory Strategy Lead]"`; items cover: confirm PMOA from mechanism, confirm center follows PMOA, confirm pathway matches center, verify precedent analogy, obtain Regulatory Strategy sign-off. Metadata id `"product_description"`; flag keys `pmoa_flags`, `lead_center_flags`, `pathway_flags`; `pmoa_checklist`, `disclaimer`, `ledger_summary`.

- [ ] **Step 6: Tests (exact)** — `score_threshold=7.5`. `test_does_not_converge_when_lead_center_flags_present` with `== ["Proposed CDRH lead center inconsistent with drug PMOA"]`; `test_stops_at_sibling_header`. Plus standard cases.

- [ ] **Step 7: Run** → PASS.

- [ ] **Step 8: Example** — scenario: **a prefilled single-dose autoinjector delivering a biologic** (drug/biologic + device constituents; generic category, NO brand). `workspace_dir="/tmp/pmoa-example"`.

- [ ] **Step 9: Skill templates** — `pmoa_{initial,revision,review,checklist}.md`.

- [ ] **Step 10: Commit**
```bash
git add src/adv_multi_agent/lifesciences/workflows/combination_product_pmoa.py tests/unit/test_combination_product_pmoa.py examples/lifesciences/combination_product_pmoa.py src/adv_multi_agent/lifesciences/skills/templates/pmoa_*.md
git commit -m "feat(lifesciences): add CombinationProductPMOAWorkflow (no-veto, 21 CFR 3 routing)"
```

---

## Task 4: `AssayPerformanceClaimWorkflow` (#2, veto) — Diagnostics

**Skeleton:** clone `src/adv_multi_agent/healthcare/workflows/adverse_event_triage.py` (named-list, veto). This is the **first veto workflow** — get `_extract_veto` / `_compose_output` / `_VETO_BANNER` / `first_draft` / audit-write-before-veto-check exactly right here; the remaining veto tasks reuse this shape.

**Files:**
- Create: `src/adv_multi_agent/lifesciences/workflows/assay_performance_claim.py`
- Test: `tests/unit/test_assay_performance_claim.py`
- Create: `examples/lifesciences/assay_performance_claim.py`
- Create: `.../skills/templates/assay_{initial,revision,review,checklist}.md`

- [ ] **Step 1: Constants** — PRODUCTION_GAPS: LIMS, CLSI EP-protocol study data, clinical-study database, labeling-management system.
```python
_MAX_FIELD_CHARS = 1500
_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated assay performance-claim review is "
    "decision-support, not IVD labeling and not a regulatory submission. A "
    "qualified Diagnostics Regulatory / R&D reviewer must independently verify "
    "every performance claim against the underlying study data before any label "
    "is released. Not legal or medical advice."
)
_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer identified "
    "a performance claim the study data do not support to a degree that risks "
    "misdiagnosis or an adulteration/misbranding exposure. See "
    "metadata['veto_reason']. Escalate to Diagnostics Regulatory; do not release "
    "the claim."
)
_FLAG_HEADERS = ("SENSITIVITY-CLAIM FLAGS:", "SPECIFICITY-CLAIM FLAGS:", "INTERFERENCE FLAGS:")
```

- [ ] **Step 2: Review criteria (full, with veto block + FORMAT NOTE)**
```python
_ASSAY_REVIEW_CRITERIA = """\
Evaluate this assay performance-claim review on five dimensions. Score each 0–10.

1. SENSITIVITY-CLAIM SUPPORT (30%) — CRITICAL
   Does each clinical/analytical sensitivity claim stay within what the study n
   and its confidence interval support? Penalise a point-estimate claim that
   ignores the lower CI bound or an underpowered n. Flag under
   SENSITIVITY-CLAIM FLAGS:.

2. SPECIFICITY-CLAIM SUPPORT (25%) — CRITICAL
   Is the specificity / false-positive-rate claim supported by the data and its
   CI? Penalise an overstated specificity claim. Flag under SPECIFICITY-CLAIM FLAGS:.

3. INTERFERENCE / CROSS-REACTIVITY (20%) — CRITICAL
   Are interferents and cross-reactants tested for every claimed matrix and
   population? Penalise a claimed matrix with untested interferents. Flag under
   INTERFERENCE FLAGS:.

4. STUDY-DESIGN ADEQUACY (15%)
   Is the study design adequate (CLSI EP protocol, appropriate reference method,
   representative population) to support the claim set? Penalise design gaps.

5. ACTIONABILITY (10%)
   Is each finding specific enough for R&D to resolve (which claim, which study,
   which interferent)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a performance claim is overstated enough that releasing it would
create a misdiagnosis risk or an adulteration/misbranding exposure (a claim the
data cannot support in the claimed intended-use population).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SENSITIVITY-CLAIM FLAGS AND zero SPECIFICITY-CLAIM FLAGS
AND zero INTERFERENCE FLAGS AND no VETO: ready for Diagnostics Regulatory
sign-off. Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SENSITIVITY-CLAIM FLAGS: [bullet list, or "None detected"]
  SPECIFICITY-CLAIM FLAGS: [bullet list, or "None detected"]
  INTERFERENCE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""
```

- [ ] **Step 3: Prompts** — Initial sections:
```
## Claim-by-claim data mapping
## Sensitivity assessment
## Specificity assessment
## Interference and cross-reactivity
## Recommended claim set
## Claims
```
Revision instruction: *"For any SENSITIVITY/SPECIFICITY flag: re-state the claim within the study CI, or remove it. For any INTERFERENCE flag: restrict the claimed matrix/population to what was tested."*

- [ ] **Step 4: Request dataclass** — fields: `assay_description`, `intended_use`, `analyte_measurand`, `claim_set`, `study_design_summary`, `interference_panel_tested`, `cross_reactivity_data`, `stability_claims`.

- [ ] **Step 5: Workflow class** — clone the `AdverseEventTriageWorkflow` named-list loop exactly, renaming the three flag lists to `current_sensitivity_flags` / `current_specificity_flags` / `current_interference_flags` (+ `all_*`). Keep: audit-write before `_extract_veto`, veto breaks first, `_compose_output`, `first_draft` on veto, `vetoed=True`. `_build_assay_checklist` owner `"[OWNER: Diagnostics Regulatory + R&D]"`; veto line first when vetoed; per-flag lines; static items: re-state claims within CI, restrict claimed matrix to tested interferents, confirm CLSI EP study design, obtain Diagnostics Regulatory sign-off. Metadata id `"assay_description"`; flag keys `sensitivity_claim_flags`, `specificity_claim_flags`, `interference_flags`; on veto add `veto_reason`, `vetoed`, `first_draft`.

- [ ] **Step 6: Tests (exact + veto)** — mirror `test_adverse_event_triage.py` fully (`score_threshold=8.0`):
  - `TestConvergence.test_converges_clean`; `test_does_not_converge_when_sensitivity_flags_present` → `assert result.metadata["sensitivity_claim_flags"] == ["Sensitivity claim 99% exceeds lower CI bound 94%"]`.
  - `test_stops_at_sibling_header` (trailing `RECOMMENDATION:` not slurped into `sensitivity_claim_flags`).
  - `TestVeto.test_veto_halts_loop`: veto critique with all-flags-None + a `REVIEWER VETO:` directive; assert `rounds == 1`, `"veto_reason" in metadata`, `metadata["vetoed"] is True`, `metadata["first_draft"] == "initial draft"`, `_VETO_BANNER in result.output`.
  - `test_no_veto_when_directive_is_none`.
  - `TestMetadata` (keys + `checklist[0] == "[OWNER: Diagnostics Regulatory + R&D]"`); `TestDisclaimer`; `TestScoreThresholdBoundary`.

- [ ] **Step 7: Run** → PASS.

- [ ] **Step 8: Example** — scenario: **a rapid antigen test** claiming 99% sensitivity where the study n supports only ~94% lower CI (generic category, NO brand) → reviewer VETO path. `workspace_dir="/tmp/assay-claim-example"`. Include the `if result.metadata.get("vetoed"):` print block from the healthcare example.

- [ ] **Step 9: Skill templates** — `assay_{initial,revision,review,checklist}.md`.

- [ ] **Step 10: Commit**
```bash
git add src/adv_multi_agent/lifesciences/workflows/assay_performance_claim.py tests/unit/test_assay_performance_claim.py examples/lifesciences/assay_performance_claim.py src/adv_multi_agent/lifesciences/skills/templates/assay_*.md
git commit -m "feat(lifesciences): add AssayPerformanceClaimWorkflow (veto, IVD performance claims)"
```

---

## Task 5: `SubstantialEquivalence510kWorkflow` (#1, veto) — Devices

**Skeleton:** clone the veto skeleton (as validated in Task 4). Note: "510(k)" appears only in prose/criteria, **never as a flag header** (H-IND-1 — headers are `PREDICATE-MISMATCH` / `INDICATION-CREEP` / `TECHNOLOGY-DELTA`, no digits/parens).

**Files:**
- Create: `src/adv_multi_agent/lifesciences/workflows/substantial_equivalence_510k.py`
- Test: `tests/unit/test_substantial_equivalence_510k.py`
- Create: `examples/lifesciences/substantial_equivalence_510k.py`
- Create: `.../skills/templates/se510k_{initial,revision,review,checklist}.md`

- [ ] **Step 1: Constants** — PRODUCTION_GAPS: FDA 510(k) clearance database + product-classification database (21 CFR 862–892), eSTAR builder, prior-submission archive.
```python
_MAX_FIELD_CHARS = 1500
_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated substantial-equivalence rationale is "
    "decision-support, not a 510(k) submission and not an FDA clearance. A "
    "qualified Regulatory Affairs lead must independently confirm predicate "
    "validity, indications scope, and technological equivalence before any "
    "submission. Not legal or medical advice."
)
_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found the "
    "substantial-equivalence claim fundamentally unsupportable (near-certain "
    "Not-Substantially-Equivalent); asserting it would misrepresent equivalence "
    "to FDA. See metadata['veto_reason']. Escalate to Regulatory Affairs; "
    "consider De Novo / PMA."
)
_FLAG_HEADERS = ("PREDICATE-MISMATCH FLAGS:", "INDICATION-CREEP FLAGS:", "TECHNOLOGY-DELTA FLAGS:")
```

- [ ] **Step 2: Review criteria (full, veto + FORMAT NOTE)**
```python
_SE_REVIEW_CRITERIA = """\
Evaluate this substantial-equivalence rationale on five dimensions. Score each 0–10.

1. PREDICATE VALIDITY (30%) — CRITICAL
   Does the candidate predicate share the same intended use and device type,
   making it a valid SE anchor? Penalise a predicate with a different intended
   use or device type. Flag under PREDICATE-MISMATCH FLAGS:.

2. INDICATIONS SCOPE (25%) — CRITICAL
   Are the subject device's indications-for-use within the predicate's cleared
   indications? Penalise indications broader than the predicate's. Flag under
   INDICATION-CREEP FLAGS:.

3. TECHNOLOGICAL DIFFERENCES (20%) — CRITICAL
   Do new technological characteristics raise new questions of safety or
   effectiveness (the Not-Substantially-Equivalent trigger)? Penalise a
   difference that raises a new question but is argued away. Flag under
   TECHNOLOGY-DELTA FLAGS:.

4. PERFORMANCE-DATA SUFFICIENCY (15%)
   Do the performance data actually address each identified difference?
   Penalise differences with no supporting data.

5. ACTIONABILITY (10%)
   Is each finding specific enough for RA to resolve (which predicate, which
   indication, which characteristic)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the substantial-equivalence claim is fundamentally unsupportable
(near-certain NSE — no valid predicate, or a technological difference that
plainly raises a new question of safety/effectiveness) such that asserting SE
would misrepresent equivalence to FDA.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero PREDICATE-MISMATCH FLAGS AND zero INDICATION-CREEP FLAGS
AND zero TECHNOLOGY-DELTA FLAGS AND no VETO: ready for Regulatory Affairs
sign-off. Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PREDICATE-MISMATCH FLAGS: [bullet list, or "None detected"]
  INDICATION-CREEP FLAGS: [bullet list, or "None detected"]
  TECHNOLOGY-DELTA FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""
```

- [ ] **Step 3: Prompts** — Initial sections:
```
## Predicate comparison
## Intended use and indications
## Technological characteristics
## Performance-data bridge
## Substantial-equivalence conclusion
## Claims
```
Revision instruction: *"For any PREDICATE-MISMATCH flag: select a predicate with matching intended use, or acknowledge NSE. For INDICATION-CREEP: narrow the subject indications to the predicate's cleared scope. For TECHNOLOGY-DELTA: cite performance data that resolves the new question, or acknowledge it is unresolved."*

- [ ] **Step 4: Request dataclass** — fields: `subject_device_description`, `intended_use`, `indications_for_use`, `technological_characteristics`, `candidate_predicates`, `performance_data_summary`, `differences_from_predicate`, `prior_fda_interactions`.

- [ ] **Step 5: Workflow class** — clone veto loop. Flag lists `current_predicate_flags` / `current_indication_flags` / `current_technology_flags`. `_build_se_checklist` owner `"[OWNER: Regulatory Affairs Lead]"`; veto line first when vetoed; items: confirm predicate intended-use match, narrow indications to cleared scope, resolve each technological difference with data, obtain RA sign-off before submission. Metadata id `"subject_device_description"`; flag keys `predicate_mismatch_flags`, `indication_creep_flags`, `technology_delta_flags`.

- [ ] **Step 6: Tests (exact + veto)** — `score_threshold=8.0`. `test_does_not_converge_when_predicate_mismatch_flags_present` → `== ["Predicate has a different intended use (diagnostic vs monitoring)"]`; `test_stops_at_sibling_header`; full veto pair; metadata (`checklist[0] == "[OWNER: Regulatory Affairs Lead]"`); disclaimer; threshold boundary.

- [ ] **Step 7: Run** → PASS.

- [ ] **Step 8: Example** — scenario: a **510(k)** for **a blood-glucose meter** claiming SE to a cleared predicate but with a broadened OTC indication (generic category, NO brand). `workspace_dir="/tmp/se510k-example"`.

- [ ] **Step 9: Skill templates** — `se510k_{initial,revision,review,checklist}.md`.

- [ ] **Step 10: Commit**
```bash
git add src/adv_multi_agent/lifesciences/workflows/substantial_equivalence_510k.py tests/unit/test_substantial_equivalence_510k.py examples/lifesciences/substantial_equivalence_510k.py src/adv_multi_agent/lifesciences/skills/templates/se510k_*.md
git commit -m "feat(lifesciences): add SubstantialEquivalence510kWorkflow (veto, predicate/NSE)"
```

---

## Task 6: `PromotionalOffLabelReviewWorkflow` (#3, veto) — Pharma/Device (MLR)

**Skeleton:** clone the veto skeleton.

**Files:**
- Create: `src/adv_multi_agent/lifesciences/workflows/promotional_off_label_review.py`
- Test: `tests/unit/test_promotional_off_label_review.py`
- Create: `examples/lifesciences/promotional_off_label_review.py`
- Create: `.../skills/templates/promo_{initial,revision,review,checklist}.md`

- [ ] **Step 1: Constants** — PRODUCTION_GAPS: promotional-review DAM (e.g. a PromoMats-class system), approved-labeling repository, claims/reference library.
```python
_MAX_FIELD_CHARS = 1500
_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated promotional-material review is "
    "decision-support, not MLR approval and not a regulatory clearance. A "
    "qualified MLR committee (Medical, Legal, Regulatory) must independently "
    "confirm on-label consistency, fair balance, and substantiation before any "
    "material is released. Not legal or medical advice."
)
_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found the "
    "material would likely draw an FDA enforcement/untitled letter (clear "
    "off-label promotion or omission of material risk). See "
    "metadata['veto_reason']. Escalate to MLR; do not release the material."
)
_FLAG_HEADERS = ("OFF-LABEL FLAGS:", "FAIR-BALANCE FLAGS:", "SUBSTANTIATION FLAGS:")
```

- [ ] **Step 2: Review criteria (full, veto + FORMAT NOTE)**
```python
_PROMO_REVIEW_CRITERIA = """\
Evaluate this promotional-material review on five dimensions. Score each 0–10.

1. ON-LABEL CONSISTENCY (30%) — CRITICAL
   Is every claim within the approved indication, population, and dosing?
   Penalise any claim outside the approved label. Flag under OFF-LABEL FLAGS:.

2. FAIR BALANCE (25%) — CRITICAL
   Is risk / limitation information present and comparably prominent to the
   benefit claims? Penalise absent or de-emphasised risk information. Flag under
   FAIR-BALANCE FLAGS:.

3. CLAIM SUBSTANTIATION (20%) — CRITICAL
   Is each efficacy / comparative / superiority claim backed by substantial
   evidence or an adequate head-to-head citation? Penalise unsupported or
   inadequately cited claims. Flag under SUBSTANTIATION FLAGS:.

4. REFERENCE ADEQUACY (15%)
   Do the cited references actually support the claims they are attached to?
   Penalise references that do not support the claim.

5. ACTIONABILITY (10%)
   Is each finding specific enough for the MLR reviewer to resolve (which claim,
   which risk, which reference)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the material would likely draw an FDA enforcement or untitled
letter — clear off-label promotion, or omission of material risk information.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero OFF-LABEL FLAGS AND zero FAIR-BALANCE FLAGS AND zero
SUBSTANTIATION FLAGS AND no VETO: ready for MLR sign-off. Otherwise: requires
revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  OFF-LABEL FLAGS: [bullet list, or "None detected"]
  FAIR-BALANCE FLAGS: [bullet list, or "None detected"]
  SUBSTANTIATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""
```

- [ ] **Step 3: Prompts** — Initial sections:
```
## Claim-by-claim label check
## Fair-balance assessment
## Substantiation and references
## Comparative-claim check
## Redline recommendations
## Claims
```
Revision instruction: *"For any OFF-LABEL flag: remove the claim or restrict it to the approved indication. For FAIR-BALANCE: add risk information with comparable prominence. For SUBSTANTIATION: attach an adequate citation or remove the claim."*

- [ ] **Step 4: Request dataclass** — fields: `material_type`, `target_audience`, `promo_claims`, `approved_labeling_reference`, `cited_references`, `risk_information_present`, `comparative_claims`.

- [ ] **Step 5: Workflow class** — clone veto loop. Flag lists `current_off_label_flags` / `current_fair_balance_flags` / `current_substantiation_flags`. `_build_promo_checklist` owner `"[OWNER: MLR Committee (Medical + Legal + Regulatory)]"`; veto line first when vetoed; items: remove/restrict off-label claims, add comparably-prominent risk info, attach adequate substantiation, obtain MLR sign-off. Metadata id `"material_type"`; flag keys `off_label_flags`, `fair_balance_flags`, `substantiation_flags`.

- [ ] **Step 6: Tests (exact + veto)** — `score_threshold=8.0`. `test_does_not_converge_when_off_label_flags_present` → `== ["Claim promotes use in a population outside the approved indication"]`; `test_stops_at_sibling_header`; veto pair; metadata (`checklist[0] == "[OWNER: MLR Committee (Medical + Legal + Regulatory)]"`); disclaimer; threshold.

- [ ] **Step 7: Run** → PASS.

- [ ] **Step 8: Example** — scenario: an **HCP visual aid for an established pharmaceutical** making an off-label population claim with under-prominent risk info (generic category, NO brand) → VETO. `workspace_dir="/tmp/promo-review-example"`.

- [ ] **Step 9: Skill templates** — `promo_{initial,revision,review,checklist}.md`.

- [ ] **Step 10: Commit**
```bash
git add src/adv_multi_agent/lifesciences/workflows/promotional_off_label_review.py tests/unit/test_promotional_off_label_review.py examples/lifesciences/promotional_off_label_review.py src/adv_multi_agent/lifesciences/skills/templates/promo_*.md
git commit -m "feat(lifesciences): add PromotionalOffLabelReviewWorkflow (veto, MLR fair-balance)"
```

---

## Task 7: `DeviceReportabilityWorkflow` (#4, veto) — Devices post-market — BOUNDARY vs healthcare

**Skeleton:** clone the veto skeleton. **D-LIFESCI-2 boundary:** the module docstring MUST state this is **distinct from the healthcare `AdverseEventTriageWorkflow`** — that one grades clinical severity/causality for a provider; this decides the *manufacturer's* regulatory reportability (MDR / vigilance) and statutory clock. A test asserts the boundary phrase is present.

**Files:**
- Create: `src/adv_multi_agent/lifesciences/workflows/device_reportability.py`
- Test: `tests/unit/test_device_reportability.py`
- Create: `examples/lifesciences/device_reportability.py`
- Create: `.../skills/templates/reportability_{initial,revision,review,checklist}.md`

- [ ] **Step 1: Constants** — Docstring includes the verbatim boundary sentence:
  `"BOUNDARY (D-LIFESCI-2): distinct from the healthcare AdverseEventTriageWorkflow — that workflow grades clinical severity/causality for a provider; this decides the manufacturer's regulatory reportability (21 CFR 803 MDR / regional vigilance) and statutory clock."`
  PRODUCTION_GAPS: complaint-handling system (e.g. a TrackWise-class QMS), FDA eMDR, EU EUDAMED vigilance, reportability decision-tree engine.
```python
_MAX_FIELD_CHARS = 1500
_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated device-reportability determination is "
    "decision-support, not a regulatory filing. A qualified Post-market "
    "Surveillance / Vigilance officer must independently confirm reportability "
    "and the statutory clock under 21 CFR 803 / regional vigilance before any "
    "decision to report or not report. Not legal or medical advice."
)
_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "'non-reportable' determination that is actually reportable under the "
    "applicable regulation. See metadata['veto_reason']. Escalate to the "
    "Vigilance officer; initiate the report within the statutory clock."
)
_FLAG_HEADERS = ("REPORTABILITY FLAGS:", "SERIOUS-INJURY FLAGS:", "MALFUNCTION-TREND FLAGS:")
```

- [ ] **Step 2: Review criteria (full, veto + FORMAT NOTE)**
```python
_REPORTABILITY_REVIEW_CRITERIA = """\
Evaluate this device-reportability determination on five dimensions. Score each 0–10.

1. REPORTABILITY DETERMINATION (30%) — CRITICAL
   Does the event meet a reporting definition (death, serious injury, or a
   malfunction likely to cause/contribute to death or serious injury if it
   recurs)? Penalise a reportable event coded non-reportable. Flag under
   REPORTABILITY FLAGS:.

2. OUTCOME GRADING (25%) — CRITICAL
   Is the outcome graded correctly — is a reportable serious injury under-graded
   as minor? Penalise under-grading of patient impact. Flag under
   SERIOUS-INJURY FLAGS:.

3. MALFUNCTION TREND (20%) — CRITICAL
   Does a recurring malfunction cross a trend / threshold reporting trigger that
   the single event masks? Penalise a trend the determination ignores. Flag
   under MALFUNCTION-TREND FLAGS:.

4. REGULATORY-CLOCK FIT (15%)
   Is the statutory clock correct for the determination (21 CFR 803 timelines /
   regional vigilance)? Penalise an incorrect or unstated clock.

5. ACTIONABILITY (10%)
   Is the determination specific enough to act on (report path, clock, trend
   basis)? Penalise vague determinations.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a 'non-reportable' determination is actually reportable under
the applicable regulation (21 CFR 803 / regional vigilance).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero REPORTABILITY FLAGS AND zero SERIOUS-INJURY FLAGS AND
zero MALFUNCTION-TREND FLAGS AND no VETO: ready for Vigilance officer sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  REPORTABILITY FLAGS: [bullet list, or "None detected"]
  SERIOUS-INJURY FLAGS: [bullet list, or "None detected"]
  MALFUNCTION-TREND FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""
```

- [ ] **Step 3: Prompts** — Initial sections:
```
## Event summary
## Reportability determination
## Outcome grading
## Malfunction-trend assessment
## Statutory clock and report path
## Claims
```
Revision instruction: *"For any REPORTABILITY flag: re-apply the reporting definition and state the clock. For SERIOUS-INJURY: re-grade the outcome against the definition. For MALFUNCTION-TREND: account for prior_similar_events_count against the trend trigger."*

- [ ] **Step 4: Request dataclass** — fields: `complaint_narrative`, `device_identifier`, `event_outcome`, `patient_impact`, `malfunction_recurrence_potential`, `prior_similar_events_count`, `market_regions`, `date_became_aware`.

- [ ] **Step 5: Workflow class** — clone veto loop. Flag lists `current_reportability_flags` / `current_serious_injury_flags` / `current_malfunction_trend_flags`. `_build_reportability_checklist` owner `"[OWNER: Post-market Surveillance / Vigilance Officer]"`; veto line first; items: re-apply reporting definition + clock, re-grade outcome, evaluate trend vs prior events, file within statutory clock, obtain Vigilance sign-off. Metadata id `"device_identifier"`; flag keys `reportability_flags`, `serious_injury_flags`, `malfunction_trend_flags`.

- [ ] **Step 6: Tests (exact + veto + boundary)** — `score_threshold=8.0`. Standard veto-workflow set, plus:
```python
def test_module_docstring_states_healthcare_boundary(self) -> None:
    import adv_multi_agent.lifesciences.workflows.device_reportability as mod
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "distinct from" in doc and "adverseeventtriage" in doc.replace(" ", "")
```
`test_does_not_converge_when_reportability_flags_present` → `== ["Serious injury coded non-reportable"]`; `test_stops_at_sibling_header`; veto pair; metadata (`checklist[0] == "[OWNER: Post-market Surveillance / Vigilance Officer]"`); disclaimer; threshold.

- [ ] **Step 7: Run** → PASS.

- [ ] **Step 8: Example** — scenario: a complaint on **an infusion pump** where a serious injury is coded non-reportable and a recurrence trend is ignored (generic category, NO brand) → VETO. `workspace_dir="/tmp/device-reportability-example"`.

- [ ] **Step 9: Skill templates** — `reportability_{initial,revision,review,checklist}.md`.

- [ ] **Step 10: Commit**
```bash
git add src/adv_multi_agent/lifesciences/workflows/device_reportability.py tests/unit/test_device_reportability.py examples/lifesciences/device_reportability.py src/adv_multi_agent/lifesciences/skills/templates/reportability_*.md
git commit -m "feat(lifesciences): add DeviceReportabilityWorkflow (veto, MDR; distinct from healthcare)"
```

---

## Task 8: `FieldActionClassificationWorkflow` (#5, veto) — Devices post-market — BOUNDARY vs industrial

**Skeleton:** clone the veto skeleton. **D-LIFESCI-2 boundary:** the module docstring MUST state this is **distinct from the industrial `RecallScopeManufacturingWorkflow`** — that scopes a general product recall; this assigns an FDA medical-device recall **class (I/II/III)** and the 21 CFR 806 correction-vs-removal reportability call. A test asserts the boundary phrase.

**Files:**
- Create: `src/adv_multi_agent/lifesciences/workflows/field_action_classification.py`
- Test: `tests/unit/test_field_action_classification.py`
- Create: `examples/lifesciences/field_action_classification.py`
- Create: `.../skills/templates/fieldaction_{initial,revision,review,checklist}.md`

- [ ] **Step 1: Constants** — Docstring boundary sentence:
  `"BOUNDARY (D-LIFESCI-2): distinct from the industrial RecallScopeManufacturingWorkflow — that scopes a general product recall; this assigns an FDA medical-device recall class (I/II/III) and the 21 CFR 806 correction-vs-removal reportability call."`
  PRODUCTION_GAPS: complaint/CAPA system, FDA Recall Enterprise System, health-hazard-evaluation board, UDI / lot-genealogy traceability.
```python
_MAX_FIELD_CHARS = 1500
_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated field-action classification is "
    "decision-support, not an FDA recall determination. A qualified Recall "
    "committee / Chief Quality Officer must independently confirm the recall "
    "class, health-hazard evaluation, and 21 CFR 806 reportability before any "
    "field action. Not legal or medical advice."
)
_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "recall-class downgrade or 'not reportable' call that leaves patients "
    "exposed. See metadata['veto_reason']. Escalate to the Recall committee / "
    "CQO; do not under-scope the action."
)
_FLAG_HEADERS = ("RECALL-CLASS FLAGS:", "CORRECTION-REMOVAL FLAGS:", "HEALTH-HAZARD FLAGS:")
```

- [ ] **Step 2: Review criteria (full, veto + FORMAT NOTE)**
```python
_FIELD_ACTION_REVIEW_CRITERIA = """\
Evaluate this field-action classification on five dimensions. Score each 0–10.

1. RECALL CLASSIFICATION (30%) — CRITICAL
   Is the proposed recall class consistent with the health hazard? Penalise a
   Class II proposed where a reasonable probability of serious adverse health
   consequences indicates Class I. Flag under RECALL-CLASS FLAGS:.

2. CORRECTION-REMOVAL REPORTABILITY (25%) — CRITICAL
   Is a 21 CFR 806 reportable correction/removal correctly characterised, and
   not mislabelled as a non-reportable enhancement or routine stock recovery?
   Penalise a reportable action characterised as non-reportable. Flag under
   CORRECTION-REMOVAL FLAGS:.

3. HEALTH-HAZARD EVALUATION (20%) — CRITICAL
   Does the health-hazard evaluation state probability, severity, and affected
   population without understating any? Penalise an evaluation that understates
   the hazard. Flag under HEALTH-HAZARD FLAGS:.

4. SCOPE COMPLETENESS (15%)
   Are affected lots/serials and distribution scope complete for the root cause?
   Penalise an under-scoped lot/distribution list.

5. ACTIONABILITY (10%)
   Is the classification specific enough to act on (class, reportability call,
   scope)? Penalise vague classification.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a recall-class downgrade or a 'not reportable' call would leave
patients exposed to a hazard that the correct class/reportability would address.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero RECALL-CLASS FLAGS AND zero CORRECTION-REMOVAL FLAGS AND
zero HEALTH-HAZARD FLAGS AND no VETO: ready for Recall committee sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  RECALL-CLASS FLAGS: [bullet list, or "None detected"]
  CORRECTION-REMOVAL FLAGS: [bullet list, or "None detected"]
  HEALTH-HAZARD FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""
```

- [ ] **Step 3: Prompts** — Initial sections:
```
## Problem and root cause
## Health-hazard evaluation
## Recall classification
## Correction vs removal reportability
## Scope (lots / distribution)
## Claims
```
Revision instruction: *"For any RECALL-CLASS flag: re-derive the class from the health hazard. For CORRECTION-REMOVAL: apply the 21 CFR 806 reportability test. For HEALTH-HAZARD: re-state probability/severity/population without understating."*

- [ ] **Step 4: Request dataclass** — fields: `problem_description`, `health_hazard_evaluation`, `affected_lots_serials`, `distribution_scope`, `action_type`, `root_cause_summary`, `patient_exposure_estimate`, `prior_related_actions`.

- [ ] **Step 5: Workflow class** — clone veto loop. Flag lists `current_recall_class_flags` / `current_correction_removal_flags` / `current_health_hazard_flags`. `_build_field_action_checklist` owner `"[OWNER: Recall Committee / Chief Quality Officer]"`; veto line first; items: re-derive class from hazard, apply 21 CFR 806 test, re-state health-hazard evaluation, confirm lot/distribution scope complete, obtain Recall committee sign-off. Metadata id `"action_type"`; flag keys `recall_class_flags`, `correction_removal_flags`, `health_hazard_flags`.

- [ ] **Step 6: Tests (exact + veto + boundary)** — `score_threshold=8.0`. Standard veto set plus:
```python
def test_module_docstring_states_industrial_boundary(self) -> None:
    import adv_multi_agent.lifesciences.workflows.field_action_classification as mod
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "distinct from" in doc and "recallscopemanufacturing" in doc.replace(" ", "")
```
`test_does_not_converge_when_recall_class_flags_present` → `== ["Class II proposed where serious-harm probability indicates Class I"]`; `test_stops_at_sibling_header`; veto pair; metadata (`checklist[0] == "[OWNER: Recall Committee / Chief Quality Officer]"`); disclaimer; threshold.

- [ ] **Step 7: Run** → PASS.

- [ ] **Step 8: Example** — scenario: a defective lot of **a point-of-care analyzer** where a Class I hazard is proposed as Class II and a reportable removal is called a stock recovery (generic category, NO brand) → VETO. `workspace_dir="/tmp/field-action-example"`.

- [ ] **Step 9: Skill templates** — `fieldaction_{initial,revision,review,checklist}.md`.

- [ ] **Step 10: Commit**
```bash
git add src/adv_multi_agent/lifesciences/workflows/field_action_classification.py tests/unit/test_field_action_classification.py examples/lifesciences/field_action_classification.py src/adv_multi_agent/lifesciences/skills/templates/fieldaction_*.md
git commit -m "feat(lifesciences): add FieldActionClassificationWorkflow (veto, recall class; distinct from industrial)"
```

---

## Task 9: Full gate, ship-audit, docs refresh

- [ ] **Step 1: Full local gate**

Run: `ruff check src/ tests/ examples/`
Expected: clean (fix any lint).

Run: `mypy src/`
Expected: clean (strict).

Run: `pytest tests/unit -q`
Expected: all PASS. Note the new total (prior baseline 771 library tests + the lifesciences additions).

- [ ] **Step 2: Brand tripwire re-run (now armed)**

Run: `pytest tests/unit/test_lifesciences_no_brand_names.py -v`
Expected: `test_no_brand_name_in_file` now parametrizes over all 8 workflow modules + 8 examples + templates + 8 tests, all PASS. If any FAIL, replace the offending brand with a generic category and re-run.

- [ ] **Step 3: Verify skill templates are discoverable**

Run: `python -c "from adv_multi_agent.core.skills.registry import SkillRegistry; p = SkillRegistry.bundled_skills_path('lifesciences'); import pathlib; print(len(list(pathlib.Path(p).glob('*.md'))))"`
Expected: `32`.

- [ ] **Step 4: Domain-ship security audit (per CLAUDE.md cadence)**

Spawn a focused `security-audit` (or independent code-reviewer) subagent on the new `lifesciences/` surface only. Brief blind: "New 7th domain, 8 workflows cloned from the healthcare veto/no-veto skeletons. Verify (a) shared-helper inheritance is real — every flag parse goes through `extract_flags`, every veto through `extract_veto_directive`, no private parsers reintroduced; (b) all inputs bounded — `_MAX_FIELD_CHARS=1500` per field + `sanitize_for_prompt(max_chars=6000)` at the boundary; (c) `_DISCLAIMER` injected in code, not prompt; (d) no flag header contains a digit/slash/paren (H-IND-1); (e) any input-shape attack vector specific to the regulatory request fields. Severity-tag findings + one-line verdict." Triage CRITICAL/HIGH before declaring done; MEDIUM/LOW may backlog into `production-readiness-gaps.md`.

- [ ] **Step 5: Refresh durable docs**

- `CLAUDE.md` "What this repo is": bump domain count 6→7, workflow count 36→44, add `lifesciences/` (8 MVP of 27-workflow catalog · 19 Phase-2 designs locked) to the package-layout line; update test counts.
- `README.md`: add lifesciences to the domain list/index.
- `docs/NEXT_SESSION.md`: new resume bookmark — lifesciences MVP-8 shipped, HEAD sha, what landed, Phase-2 (19) still locked, ship-audit outcome.
- `docs/production-readiness-gaps.md`: add any MEDIUM/LOW audit findings + the universal lifesciences PRODUCTION_GAPS (live source-system integrations).
- Update memory index `project_state.md` if the domain count is referenced there.

- [ ] **Step 6: Final docs commit**

```bash
git add CLAUDE.md README.md docs/NEXT_SESSION.md docs/production-readiness-gaps.md
git commit -m "docs(lifesciences): refresh repo index, resume bookmark, gaps after MVP-8 ship [skip ci]"
```

---

## Self-review (completed against the spec)

- **Spec coverage:** all 8 MVP workflows have a task (Tasks 1–8, spec build-order preserved: #7,#8,#6,#2,#1,#3,#4,#5); wiring + decisions + package-data + MCP/registry allowlists in Task 0; ship-audit + Phase-2-locked note in Task 9. The 19 Phase-2 designs are intentionally not built (D-LIFESCI-1) — no tasks, correct.
- **No-brand constraint (D-LIFESCI-3):** enforced three ways — every example names a generic category, the module/prompt text uses categories, and Task 0's tripwire (base64-seeded to keep plaintext clean) fails CI on any brand string. Autonomy decision surfaced.
- **Idiom consistency:** pinned — dict-driven for #7/#8/#6, named-list for #2/#1/#3/#4/#5. Flag-header names verified uppercase + hyphen only (H-IND-1 safe; "510(k)" kept out of headers).
- **Boundary (D-LIFESCI-2):** #4 and #5 carry the distinct-from docstring + a test asserting it.
- **Type/name consistency:** Request class names, module filenames, template prefixes, and metadata flag keys are fixed in the prefix-map table and reused verbatim across each task's steps.
- **Placeholder scan:** criteria blocks, prompts (section lists), checklist owners+items, disclaimers, and the exact test assertions are written in full; the only "reference, don't inline" is the run-loop, which points at two real on-disk files (not a placeholder).
