# Healthcare Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the healthcare domain MVP-8 per `docs/superpowers/specs/2026-05-16-healthcare-domain-design.md` — 4 non-veto and 4 veto-using workflows, 32 skill templates, 8 examples, 8 test files, MCP integration, decisions/scenarios/README/CLAUDE.md updates, and a passing security audit.

**Architecture:** Sibling package `src/adv_multi_agent/healthcare/` following the D-IND-1 convention (no domain base class; per-workflow `*Request` dataclass with `_MAX_FIELD_CHARS = 1500`; 1–3 FLAGS-class convergence gate; optional reviewer-veto via shared `extract_veto_directive`; `truncate_flag_display` in `_format_flag_section`; `_DISCLAIMER` injected in code; approver checklist). All shared parser/sanitizer/cap helpers in `core/_internal.py` are inherited as-is — no new helpers, no new flag-header character classes.

**Tech Stack:** Python 3.11+, `anthropic` SDK, plain `dataclass`, `pytest` + `pytest-asyncio`. No new dependencies.

**Reference implementations (read first):**
- Non-veto pattern: `src/adv_multi_agent/industrial/workflows/supplier_qualification.py` (381 LOC, triple-flag gate)
- Veto pattern: `src/adv_multi_agent/industrial/workflows/product_liability_root_cause.py` (515 LOC, triple-flag + veto)
- Non-veto test pattern: `tests/unit/test_supplier_qualification.py` (183 LOC)
- Veto test pattern: `tests/unit/test_product_liability_root_cause.py`
- Fakes for tests: `tests/unit/fakes.py` (`FakeExecutor`, `FakeReviewer`)

---

## File Map

**Create (47 files):**

Healthcare package skeleton (3 files):
- `src/adv_multi_agent/healthcare/__init__.py`
- `src/adv_multi_agent/healthcare/workflows/__init__.py`
- `src/adv_multi_agent/healthcare/skills/__init__.py`

Workflows (8 files):
- `src/adv_multi_agent/healthcare/workflows/diagnosis_code_audit.py`
- `src/adv_multi_agent/healthcare/workflows/discharge_planning_risk.py`
- `src/adv_multi_agent/healthcare/workflows/prior_authorization_review.py`
- `src/adv_multi_agent/healthcare/workflows/claims_appeal_review.py`
- `src/adv_multi_agent/healthcare/workflows/drug_interaction_flagging.py`
- `src/adv_multi_agent/healthcare/workflows/adverse_event_triage.py`
- `src/adv_multi_agent/healthcare/workflows/treatment_plan_review.py`
- `src/adv_multi_agent/healthcare/workflows/clinical_trial_eligibility.py`

Skill templates (32 files in `src/adv_multi_agent/healthcare/skills/templates/`):
- `diagnosis_initial.md`, `diagnosis_revision.md`, `diagnosis_review.md`, `diagnosis_checklist.md`
- `discharge_initial.md`, `discharge_revision.md`, `discharge_review.md`, `discharge_checklist.md`
- `prior_auth_initial.md`, `prior_auth_revision.md`, `prior_auth_review.md`, `prior_auth_checklist.md`
- `claims_appeal_initial.md`, `claims_appeal_revision.md`, `claims_appeal_review.md`, `claims_appeal_checklist.md`
- `drug_initial.md`, `drug_revision.md`, `drug_review.md`, `drug_checklist.md`
- `adverse_initial.md`, `adverse_revision.md`, `adverse_review.md`, `adverse_checklist.md`
- `treatment_initial.md`, `treatment_revision.md`, `treatment_review.md`, `treatment_checklist.md`
- `trial_initial.md`, `trial_revision.md`, `trial_review.md`, `trial_checklist.md`

Examples (9 files):
- `examples/healthcare/__init__.py`
- `examples/healthcare/diagnosis_code_audit.py`
- `examples/healthcare/discharge_planning_risk.py`
- `examples/healthcare/prior_authorization_review.py`
- `examples/healthcare/claims_appeal_review.py`
- `examples/healthcare/drug_interaction_flagging.py`
- `examples/healthcare/adverse_event_triage.py`
- `examples/healthcare/treatment_plan_review.py`
- `examples/healthcare/clinical_trial_eligibility.py`

Tests (8 files):
- `tests/unit/test_diagnosis_code_audit.py`
- `tests/unit/test_discharge_planning_risk.py`
- `tests/unit/test_prior_authorization_review.py`
- `tests/unit/test_claims_appeal_review.py`
- `tests/unit/test_drug_interaction_flagging.py`
- `tests/unit/test_adverse_event_triage.py`
- `tests/unit/test_treatment_plan_review.py`
- `tests/unit/test_clinical_trial_eligibility.py`

Audit doc:
- `docs/security-audits/2026-05-16-healthcare-sweep.md`

**Modify (7 files):**
- `pyproject.toml` — add `adv_multi_agent.healthcare.skills.templates` to `[tool.setuptools.package-data]`
- `src/adv_multi_agent/__init__.py` — expose `healthcare` subpackage if package-level re-exports exist (mirror prior domains)
- `src/adv_multi_agent/core/skills/registry.py` — add `"healthcare"` to `_KNOWN_DOMAINS` frozenset (L-IND-4 allowlist)
- `src/adv_multi_agent/core/skills/mcp_server.py` — no change required if domain dispatch reads `SKILLS_DOMAIN` env directly (verify in Task 1)
- `docs/decisions.md` — append D-HEALTH-1..4 rows
- `docs/scenarios.md` — update healthcare section from "candidate" to "built" for the 8 workflows
- `README.md` — bump domain count + workflow count + skill count + test count, add `SKILLS_DOMAIN=healthcare` MCP registration line
- `CLAUDE.md` — add `healthcare` to the currently-shipped-domains list

---

## Task 1: Scaffold healthcare package + register domain allowlist

**Files:**
- Create: `src/adv_multi_agent/healthcare/__init__.py`
- Create: `src/adv_multi_agent/healthcare/workflows/__init__.py`
- Create: `src/adv_multi_agent/healthcare/skills/__init__.py`
- Create: `src/adv_multi_agent/healthcare/skills/templates/` (directory)
- Create: `examples/healthcare/__init__.py`
- Modify: `src/adv_multi_agent/core/skills/registry.py` (add `"healthcare"` to `_KNOWN_DOMAINS`)
- Modify: `pyproject.toml` (add package-data row)

- [ ] **Step 1: Create the four `__init__.py` files**

`src/adv_multi_agent/healthcare/__init__.py`:
```python
"""Healthcare domain — adversarial multi-agent decision support.

See docs/superpowers/specs/2026-05-16-healthcare-domain-design.md for the
27-workflow catalog. MVP-8 is shipped; 19 Phase-2 workflows are designed
but not built.

ALL CLINICAL OUTPUT IS ADVISORY. NO WORKFLOW REPLACES CLINICAL JUDGEMENT.
"""
```

`src/adv_multi_agent/healthcare/workflows/__init__.py`:
```python
"""Healthcare workflows — MVP-8 per D-HEALTH-1."""
```

`src/adv_multi_agent/healthcare/skills/__init__.py`:
```python
"""Healthcare skill templates — 32 .md files (4 per MVP workflow)."""
```

`examples/healthcare/__init__.py`:
```python
"""Healthcare workflow examples — synthetic / de-identified inputs only."""
```

- [ ] **Step 2: Create the templates directory with a placeholder**

Run:
```bash
mkdir -p src/adv_multi_agent/healthcare/skills/templates
touch src/adv_multi_agent/healthcare/skills/templates/.gitkeep
```

- [ ] **Step 3: Add `"healthcare"` to `_KNOWN_DOMAINS` in registry.py**

Edit `src/adv_multi_agent/core/skills/registry.py`. Find:
```python
    _KNOWN_DOMAINS: frozenset[str] = frozenset(
        {"research", "parole", "retail", "pc", "industrial"}
    )
```
Change to:
```python
    _KNOWN_DOMAINS: frozenset[str] = frozenset(
        {"research", "parole", "retail", "pc", "industrial", "healthcare"}
    )
```

Also update the docstring of `bundled_skills_path` to list `"healthcare"` in the allowed values.

- [ ] **Step 4: Verify MCP server dispatches by env var**

Read `src/adv_multi_agent/core/skills/mcp_server.py`. If it reads `os.environ["SKILLS_DOMAIN"]` and passes it to `SkillRegistry.bundled_skills_path(domain)`, no further change needed — the allowlist update is sufficient. If it has a hardcoded dispatch, add a `"healthcare"` arm following the existing pattern.

- [ ] **Step 5: Add package-data row to pyproject.toml**

Edit `pyproject.toml`. Find the `[tool.setuptools.package-data]` table. Add:
```toml
"adv_multi_agent.healthcare.skills.templates" = ["*.md"]
```
Verify `[tool.setuptools.packages.find]` will pick up `adv_multi_agent.healthcare.*` automatically (it uses include = `["adv_multi_agent*"]` per prior domains).

- [ ] **Step 6: Run existing tests — verify no regression**

```bash
python -m pytest tests/ -q
```
Expected: 481 passed, 0 failed (no healthcare tests yet; nothing should break).

- [ ] **Step 7: Run mypy + ruff**

```bash
python -m mypy src/ --strict
python -m ruff check src/
```
Expected: clean (no new lint or type errors introduced).

- [ ] **Step 8: Commit**

```bash
git add src/adv_multi_agent/healthcare/ examples/healthcare/ src/adv_multi_agent/core/skills/registry.py pyproject.toml
git commit -m "feat(healthcare): scaffold package + register domain allowlist"
```

---

## Task 2: Implement `DiagnosisCodeAuditWorkflow` (worked example — non-veto)

**Files:**
- Create: `src/adv_multi_agent/healthcare/workflows/diagnosis_code_audit.py`
- Create: `tests/unit/test_diagnosis_code_audit.py`
- Create: `examples/healthcare/diagnosis_code_audit.py`
- Create: 4 skill templates under `src/adv_multi_agent/healthcare/skills/templates/`:
  - `diagnosis_initial.md`
  - `diagnosis_revision.md`
  - `diagnosis_review.md`
  - `diagnosis_checklist.md`

**Design spec section:** "5. PriorAuthorizationReviewWorkflow" through "7. DiagnosisCodeAuditWorkflow" in `docs/superpowers/specs/2026-05-16-healthcare-domain-design.md`.

**Per-workflow spec (from D-HEALTH-1 design):**
- Request fields (all `str`, all sliced by `_MAX_FIELD_CHARS = 1500`):
  - `encounter_summary`, `proposed_codes`, `provider_specialty`, `payer_guidelines`, `previous_audits`, `clinical_context`
- Flag headers: `ACCURACY FLAGS:`, `COMPLIANCE FLAGS:`, `SPECIFICITY FLAGS:`
- Score threshold: 7.5
- No veto
- Checklist owner: health information manager / certified coder (CCS/CPC)

**Reference structure:** `src/adv_multi_agent/industrial/workflows/supplier_qualification.py` (triple-flag, no veto). Read it first.

- [ ] **Step 1: Write the failing test file**

Create `tests/unit/test_diagnosis_code_audit.py`:
```python
"""Unit tests for DiagnosisCodeAuditWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.healthcare.workflows.diagnosis_code_audit import (
    DiagnosisCodeAuditWorkflow,
    DiagnosisCodeAuditRequest,
    _DISCLAIMER,
    _MAX_FIELD_CHARS,
)
from .fakes import FakeExecutor, FakeReviewer


def make_config(tmp_path: Path, **kwargs: Any) -> Config:
    defaults: dict[str, Any] = dict(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=3,
        score_threshold=7.5,
    )
    defaults.update(kwargs)
    return Config(**defaults)


def make_review(
    score: float,
    *,
    approved: bool,
    critique: str = "",
    suggestions: list[str] | None = None,
) -> ReviewResult:
    return ReviewResult(
        score=score,
        critique=critique,
        suggestions=suggestions or [],
        approved=approved,
    )


def make_request(**kwargs: Any) -> DiagnosisCodeAuditRequest:
    defaults: dict[str, Any] = dict(
        encounter_summary="65yo M admitted with NSTEMI, cath shows 90% LAD lesion, "
                          "PCI with DES placed. PMH HTN, DM2, CKD3. LOS 3 days.",
        proposed_codes="I21.4 (NSTEMI); E11.22 (DM2 w/CKD); I12.9 (HTN w/CKD); "
                       "N18.30 (CKD3); 92928 (PCI single vessel w/DES)",
        provider_specialty="cardiology",
        payer_guidelines="Medicare LCD L33797; AHA Coding Clinic Q2 2025",
        previous_audits="Prior audit flagged undercoding of CKD stage specificity",
        clinical_context="Inpatient admission; PCI procedure; 3-day LOS",
    )
    defaults.update(kwargs)
    return DiagnosisCodeAuditRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        request = make_request()
        text = request.to_prompt_text()
        assert "Encounter summary:" in text
        assert "Proposed codes:" in text
        assert "Provider specialty:" in text
        assert "Payer guidelines:" in text
        assert "Previous audits:" in text
        assert "Clinical context:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        # L-PC-3 invariant — oversized field is sliced to _MAX_FIELD_CHARS
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        request = make_request(encounter_summary=oversized)
        text = request.to_prompt_text()
        # The truncated field appears at most _MAX_FIELD_CHARS x's after the label
        encounter_section = text.split("Encounter summary:")[1].split("\n")[0]
        assert len(encounter_section.strip()) <= _MAX_FIELD_CHARS + 5  # +5 for whitespace


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_on_first_round_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(outputs=["## Codes\nI21.4 — accurate"])
        reviewer = FakeReviewer(results=[
            make_review(
                8.5,
                approved=True,
                critique="ACCURACY FLAGS: None detected\n"
                        "COMPLIANCE FLAGS: None detected\n"
                        "SPECIFICITY FLAGS: None detected",
            )
        ])
        wf = DiagnosisCodeAuditWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_with_accuracy_flag(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(outputs=["draft 1", "draft 2", "draft 3"])
        critique_with_flag = (
            "ACCURACY FLAGS:\n"
            "  - I12.9 should be I12.0 given CKD3 + HTN per AHA Coding Clinic\n"
            "COMPLIANCE FLAGS: None detected\n"
            "SPECIFICITY FLAGS: None detected"
        )
        reviewer = FakeReviewer(results=[
            make_review(9.0, approved=True, critique=critique_with_flag),
            make_review(9.0, approved=True, critique=critique_with_flag),
            make_review(9.0, approved=True, critique=critique_with_flag),
        ])
        wf = DiagnosisCodeAuditWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3  # max_review_rounds

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(outputs=["draft 1", "draft 2"])
        reviewer = FakeReviewer(results=[
            make_review(
                9.0, approved=True,
                critique="ACCURACY FLAGS:\n  - I12.9 specificity\n"
                         "COMPLIANCE FLAGS: None detected\n"
                         "SPECIFICITY FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="ACCURACY FLAGS: None detected\n"
                         "COMPLIANCE FLAGS: None detected\n"
                         "SPECIFICITY FLAGS: None detected",
            ),
        ])
        wf = DiagnosisCodeAuditWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(outputs=["draft"])
        reviewer = FakeReviewer(results=[
            make_review(
                9.0, approved=True,
                critique="ACCURACY FLAGS: None detected\n"
                         "COMPLIANCE FLAGS: None detected\n"
                         "SPECIFICITY FLAGS: None detected",
            )
        ])
        wf = DiagnosisCodeAuditWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert "accuracy_flags" in result.metadata
        assert "compliance_flags" in result.metadata
        assert "specificity_flags" in result.metadata
        assert "audit_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(outputs=["draft"])
        reviewer = FakeReviewer(results=[
            make_review(
                9.0, approved=True,
                critique="ACCURACY FLAGS: None detected\n"
                         "COMPLIANCE FLAGS: None detected\n"
                         "SPECIFICITY FLAGS: None detected",
            )
        ])
        wf = DiagnosisCodeAuditWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
        assert "ADVISORY" in _DISCLAIMER.upper()
```

- [ ] **Step 2: Run the test — verify it fails with `ImportError`**

```bash
python -m pytest tests/unit/test_diagnosis_code_audit.py -v
```
Expected: `ImportError: cannot import name 'DiagnosisCodeAuditWorkflow'`

- [ ] **Step 3: Implement the workflow**

Create `src/adv_multi_agent/healthcare/workflows/diagnosis_code_audit.py`. Follow the structure of `src/adv_multi_agent/industrial/workflows/supplier_qualification.py` exactly (triple-flag, no veto). The Request dataclass and the per-flag-header content differ; everything else (imports, sanitize, loop, `_register_claims`, wiki feedback, flag extraction, `_format_flag_section`, checklist, return) is byte-identical pattern.

Key elements to include:
```python
"""
Workflow — Diagnosis Code Audit (Healthcare Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for ICD-10-CM/PCS and
CPT coding accuracy. Executor proposes/audits codes; reviewer (recommended:
different model family) challenges accuracy, compliance with payer guidelines,
and specificity (avoiding upcoding and undercoding).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PHI de-identification — encounter_summary is free-text; caller's
       responsibility to ensure HIPAA Safe Harbor / Expert Determination
       de-identification before submission.
    2. EHR integration — clinical documentation should be pulled from
       Epic/Cerner, not manually excerpted.
    3. Live coding reference — ICD-10-CM/PCS Official Guidelines, AHA Coding
       Clinic, and CPT Assistant should be integrated as authoritative
       references, not caller-supplied text.
    4. Certified coder review gate — all AI-suggested code changes must be
       reviewed and confirmed by a credentialed coder (CCS, CPC) before
       claim submission.
    5. RAC / OIG audit trail — any code changes must be documented with
       rationale for compliance audit purposes.
    6. Dedicated third-model coding auditor — production should use a
       separately configured auditor model for specificity bias detection.
       See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import (
    extract_flags,
    sanitize_for_prompt,
    truncate_flag_display,
)
from ...core.workflow import BaseWorkflow, WorkflowResult

# L-PC-3: per-field cap — prevents a single oversized field crowding out
# later fields when the concatenated prompt is trimmed by sanitize_for_prompt.
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated coding audit is not a billing "
    "submission. A credentialed coder (CCS, CPC) must independently verify "
    "every code change against primary documentation before any claim is "
    "submitted. AI output must never trigger automated billing."
)

_DIAGNOSIS_REVIEW_CRITERIA = """\
Evaluate this diagnosis-code audit on five dimensions. Score each 0–10.

1. CODE-TO-DOCUMENTATION ACCURACY (30%)
   Does every proposed code map to specific language in the encounter
   documentation? Are codes neither upcoded (unsupported severity/specificity)
   nor undercoded (under-documenting captured conditions)? Flag mismatches
   under ACCURACY FLAGS:.

2. GUIDELINE COMPLIANCE (25%)
   Are proposed codes consistent with ICD-10-CM Official Guidelines, AHA
   Coding Clinic, payer LCD/NCD, and CPT coding conventions? Flag deviations
   under COMPLIANCE FLAGS:.

3. SPECIFICITY (20%)
   Is the most specific code available used, or has a less-specific code
   been chosen where documentation supports specificity (e.g. CKD stage,
   diabetes complication, fracture laterality)? Flag specificity gaps under
   SPECIFICITY FLAGS:.

4. PAYER-SPECIFIC FIT (15%)
   Does the code set align with the payer's policy and DRG/APC assignment
   expectations? Penalise advice that ignores payer_guidelines.

5. ACTIONABILITY (10%)
   Are recommended changes specific enough for the coder to apply (code,
   replacement, evidence citation)?

Overall score = weighted average.
Score ≥ 7.5 AND zero ACCURACY FLAGS AND zero COMPLIANCE FLAGS AND zero
SPECIFICITY FLAGS: ready for coder review.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  ACCURACY FLAGS: [bullet list, or "None detected"]
  COMPLIANCE FLAGS: [bullet list, or "None detected"]
  SPECIFICITY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are auditing diagnosis and procedure codes for a credentialed coder to
review. You have no stake in the outcome. Audit codes against the encounter
documentation — not against general coding norms.

BASE EVERY RECOMMENDATION ON THE INPUT DOCUMENTATION. Do not import
assumptions from other cases not present in the encounter summary, codes,
or payer guidelines below.

ENCOUNTER (caller-supplied — verify against EHR before acting):
{request_text}

{wiki_context}

Produce an audit with:

## Code accuracy
- Code-by-code mapping to documentation language

## Compliance check
- ICD-10-CM Official Guidelines / AHA Coding Clinic / payer LCD references

## Specificity gaps
- Less-specific codes where documentation supports specificity

## Recommended changes
- Code | Current | Recommended | Evidence citation

## Claims
- Specific factual claims about the documentation that ground the audit
"""

_REVISION_PROMPT = """\
Revise the diagnosis-code audit based on reviewer critique.

ORIGINAL AUDIT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: REMOVE the unsupported code claim or replace it
with documentation evidence from the encounter summary. Do not rephrase.
"""


@dataclass
class DiagnosisCodeAuditRequest:
    """Structured input for the diagnosis-code audit workflow."""

    encounter_summary: str
    """Clinical documentation excerpt (H&P, discharge summary, op note)."""

    proposed_codes: str
    """ICD-10-CM/PCS or CPT codes with descriptions proposed by coder."""

    provider_specialty: str
    """Specialty context for coding conventions."""

    payer_guidelines: str
    """Payer-specific coding guidelines or LCD/NCD references."""

    previous_audits: str
    """Prior coding audit findings for this provider or encounter type."""

    clinical_context: str
    """Admission type (IP/OP/ED), procedure details, LOS."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Encounter summary: {self.encounter_summary[:cap]}",
            f"Proposed codes: {self.proposed_codes[:cap]}",
            f"Provider specialty: {self.provider_specialty[:cap]}",
            f"Payer guidelines: {self.payer_guidelines[:cap]}",
            f"Previous audits: {self.previous_audits[:cap]}",
            f"Clinical context: {self.clinical_context[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "ACCURACY FLAGS:",
    "COMPLIANCE FLAGS:",
    "SPECIFICITY FLAGS:",
)


class DiagnosisCodeAuditWorkflow(BaseWorkflow):
    """
    Adversarial diagnosis-code audit: executor proposes/audits codes →
    reviewer challenges accuracy, compliance, and specificity → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero ACCURACY FLAGS
        AND zero COMPLIANCE FLAGS
        AND zero SPECIFICITY FLAGS
    """

    async def run(  # type: ignore[override]
        self,
        request: DiagnosisCodeAuditRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
        accumulated: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
        max_wiki_chars = config.max_wiki_body_chars

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    request_text=request_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                flag_section = self._format_flag_section(current)
                prompt = _REVISION_PROMPT.format(
                    previous=sanitize_for_prompt(output, max_chars=10000),
                    score=score,
                    critique=sanitize_for_prompt(review.critique, max_chars=4000),
                    suggestions="\n".join(
                        f"- {sanitize_for_prompt(s, max_chars=500)}"
                        for s in review.suggestions
                    ),
                    flag_section=flag_section,
                    wiki_context=wiki_ctx,
                )

            output = await self.executor.run(prompt, context="")
            self._register_claims(output, round_num)

            review = await self.reviewer.review(
                output,
                criteria=_DIAGNOSIS_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            if review.approved and not any(current.values()):
                converged = True
                break

        audit_checklist = self._build_audit_checklist(request, accumulated)
        output_with_banner = f"{output}\n\n---\n\n{_DISCLAIMER}"

        metadata: dict[str, Any] = {
            "provider_specialty": request.provider_specialty,
            "accuracy_flags": list(dict.fromkeys(accumulated["ACCURACY FLAGS:"])),
            "compliance_flags": list(dict.fromkeys(accumulated["COMPLIANCE FLAGS:"])),
            "specificity_flags": list(dict.fromkeys(accumulated["SPECIFICITY FLAGS:"])),
            "audit_checklist": audit_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }

        return WorkflowResult(
            output=output_with_banner,
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata=metadata,
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "ACCURACY FLAGS:": (
                "⚠️  ACCURACY FLAGS (correct the code-to-documentation mismatch; "
                "do not infer codes beyond what the encounter supports):"
            ),
            "COMPLIANCE FLAGS:": (
                "⚠️  COMPLIANCE FLAGS (align with ICD-10-CM Official Guidelines / "
                "AHA Coding Clinic / payer LCD; cite the specific guidance):"
            ),
            "SPECIFICITY FLAGS:": (
                "⚠️  SPECIFICITY FLAGS (use the most specific code the documentation "
                "supports; do not default to unspecified codes):"
            ),
        }
        parts: list[str] = []
        for header in _FLAG_HEADERS:
            items = current[header]
            if not items:
                continue
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(items)
            )
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _build_audit_checklist(
        request: DiagnosisCodeAuditRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Health Information Manager / Certified Coder (CCS/CPC)]")
        if accumulated["ACCURACY FLAGS:"]:
            checklist.append(
                "[ ] Verify every flagged code change against primary encounter "
                "documentation before claim submission"
            )
        if accumulated["COMPLIANCE FLAGS:"]:
            checklist.append(
                "[ ] Confirm cited ICD-10-CM / AHA Coding Clinic / payer LCD "
                "references resolve to current effective-date guidance"
            )
        if accumulated["SPECIFICITY FLAGS:"]:
            checklist.append(
                "[ ] Resolve specificity gaps by querying the provider for "
                "additional documentation, not by guessing"
            )
        checklist.append(
            "[ ] Document audit rationale in the coding compliance log "
            "(RAC / OIG audit trail)"
        )
        checklist.append(
            "[ ] Submit claim only after credentialed coder sign-off"
        )
        return checklist
```

- [ ] **Step 4: Run the test — verify it passes**

```bash
python -m pytest tests/unit/test_diagnosis_code_audit.py -v
```
Expected: all 7 tests pass.

- [ ] **Step 5: Run mypy strict + ruff**

```bash
python -m mypy src/adv_multi_agent/healthcare/workflows/diagnosis_code_audit.py --strict
python -m ruff check src/adv_multi_agent/healthcare/workflows/diagnosis_code_audit.py
```
Expected: clean.

- [ ] **Step 6: Create the 4 skill templates**

`src/adv_multi_agent/healthcare/skills/templates/diagnosis_initial.md`:
```markdown
---
name: diagnosis_initial
description: Initial draft of a diagnosis-code audit; maps each proposed code to encounter documentation
inputs:
  - encounter_summary
  - proposed_codes
  - provider_specialty
  - payer_guidelines
  - clinical_context
---

You are auditing diagnosis and procedure codes for a credentialed coder.

For each proposed code in {proposed_codes}:
1. Cite the specific language in {encounter_summary} that supports the code.
2. Note any ICD-10-CM Official Guideline / AHA Coding Clinic / {payer_guidelines} reference that applies.
3. Identify whether a more specific code is available for this clinical context.

Output sections: ## Code accuracy, ## Compliance check, ## Specificity gaps, ## Recommended changes, ## Claims.

Specialty context: {provider_specialty}. Clinical context: {clinical_context}.
```

`src/adv_multi_agent/healthcare/skills/templates/diagnosis_revision.md`:
```markdown
---
name: diagnosis_revision
description: Revise diagnosis-code audit using reviewer feedback; remove or ground every flagged code claim
inputs:
  - previous
  - critique
  - flag_section
---

Revise the prior diagnosis-code audit:

ORIGINAL:
{previous}

REVIEWER CRITIQUE:
{critique}

{flag_section}

For every flagged item: REMOVE the unsupported code claim or replace it with a citation to specific language in the encounter documentation. Do not rephrase. Maintain the same section structure.
```

`src/adv_multi_agent/healthcare/skills/templates/diagnosis_review.md`:
```markdown
---
name: diagnosis_review
description: Reviewer criteria for diagnosis-code audit; ACCURACY + COMPLIANCE + SPECIFICITY flags
inputs:
  - output
---

Evaluate the diagnosis-code audit below on five dimensions (score each 0–10):

1. CODE-TO-DOCUMENTATION ACCURACY (30%) — does every code map to specific documentation language?
2. GUIDELINE COMPLIANCE (25%) — alignment with ICD-10-CM Official Guidelines, AHA Coding Clinic, payer LCD.
3. SPECIFICITY (20%) — most specific code available used where documentation supports it?
4. PAYER-SPECIFIC FIT (15%) — DRG/APC alignment with payer policy.
5. ACTIONABILITY (10%) — recommendations specific enough for the coder to apply.

Flag deviations under: ACCURACY FLAGS:, COMPLIANCE FLAGS:, SPECIFICITY FLAGS:.

End your review with:
  Overall score: X/10
  Key issues: [bullet list]
  ACCURACY FLAGS: [bullet list, or "None detected"]
  COMPLIANCE FLAGS: [bullet list, or "None detected"]
  SPECIFICITY FLAGS: [bullet list, or "None detected"]

AUDIT:
{output}
```

`src/adv_multi_agent/healthcare/skills/templates/diagnosis_checklist.md`:
```markdown
---
name: diagnosis_checklist
description: Pre-submission checklist for the certified coder to clear before any claim is submitted
inputs:
  - accuracy_flags
  - compliance_flags
  - specificity_flags
---

Owner: Health Information Manager / Certified Coder (CCS, CPC).

Before claim submission:
- [ ] Verify every flagged code change against primary encounter documentation
- [ ] Confirm cited ICD-10-CM / AHA Coding Clinic / payer LCD references resolve to current effective-date guidance
- [ ] Resolve specificity gaps by querying the provider for additional documentation, not by guessing
- [ ] Document audit rationale in the coding compliance log (RAC / OIG audit trail)
- [ ] Submit claim only after credentialed coder sign-off

Outstanding flags:
- Accuracy: {accuracy_flags}
- Compliance: {compliance_flags}
- Specificity: {specificity_flags}
```

- [ ] **Step 7: Create the example script**

`examples/healthcare/diagnosis_code_audit.py`:
```python
"""Example — DiagnosisCodeAuditWorkflow with synthetic NSTEMI + PCI encounter.

Run: python -m examples.healthcare.diagnosis_code_audit
Requires: ANTHROPIC_API_KEY (executor) + OPENAI_API_KEY (reviewer) or
SAME-FAMILY pairing (REVIEWER_PROVIDER=anthropic).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.healthcare.workflows.diagnosis_code_audit import (
    DiagnosisCodeAuditRequest,
    DiagnosisCodeAuditWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=__import__("os").environ.get("ANTHROPIC_API_KEY", ""),
        openai_api_key=__import__("os").environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir=str(Path.cwd() / ".healthcare_workspace"),
        max_review_rounds=4,
        score_threshold=7.5,
    )

    executor = ExecutorAgent(config)
    reviewer = ReviewerAgent(config)
    workflow = DiagnosisCodeAuditWorkflow(
        executor=executor, reviewer=reviewer, config=config
    )

    request = DiagnosisCodeAuditRequest(
        encounter_summary=(
            "65yo M admitted with NSTEMI. Cath shows 90% LAD lesion. "
            "PCI with DES placed. PMH: HTN, DM2 with stage-3 CKD. LOS 3 days. "
            "Discharged on dual antiplatelet therapy."
        ),
        proposed_codes=(
            "I21.4 (NSTEMI); E11.22 (DM2 w/CKD); I12.9 (HTN w/CKD unspecified); "
            "N18.30 (CKD3 unspecified); 92928 (PCI single vessel w/DES)"
        ),
        provider_specialty="cardiology",
        payer_guidelines=(
            "Medicare LCD L33797 (Cardiac Catheterization); "
            "AHA Coding Clinic Q2 2025 — HTN+CKD coding hierarchy."
        ),
        previous_audits=(
            "2025-Q1 audit found CKD stage specificity undercoded on 14% of "
            "cardiology encounters; corrective training delivered 2025-04-15."
        ),
        clinical_context="Inpatient admission; PCI procedure; 3-day LOS.",
    )

    result = await workflow.run(request=request)

    print(f"\n{'='*60}")
    print(f"Converged: {result.converged} in {result.rounds} rounds")
    print(f"Final score: {result.final_score}/10")
    print(f"{'='*60}\n")
    print(result.output)
    print(f"\n{'='*60}")
    print(f"Accuracy flags: {result.metadata['accuracy_flags']}")
    print(f"Compliance flags: {result.metadata['compliance_flags']}")
    print(f"Specificity flags: {result.metadata['specificity_flags']}")
    print(f"\nChecklist:")
    for item in result.metadata['audit_checklist']:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 8: Run the test suite again and full type/lint check**

```bash
python -m pytest tests/ -q
python -m mypy src/ --strict
python -m ruff check src/
```
Expected: 488 passed (481 prior + 7 new diagnosis tests), 0 failures, mypy + ruff clean.

- [ ] **Step 9: Commit**

```bash
git add src/adv_multi_agent/healthcare/workflows/diagnosis_code_audit.py \
        src/adv_multi_agent/healthcare/skills/templates/diagnosis_*.md \
        tests/unit/test_diagnosis_code_audit.py \
        examples/healthcare/diagnosis_code_audit.py
git commit -m "feat(healthcare): DiagnosisCodeAuditWorkflow (ACCURACY + COMPLIANCE + SPECIFICITY flags)"
```

---

## Task 3: Implement `DischargePlanningRiskWorkflow` (non-veto)

**Files:**
- Create: `src/adv_multi_agent/healthcare/workflows/discharge_planning_risk.py`
- Create: `tests/unit/test_discharge_planning_risk.py`
- Create: `examples/healthcare/discharge_planning_risk.py`
- Create: 4 skill templates (`discharge_initial.md`, `discharge_revision.md`, `discharge_review.md`, `discharge_checklist.md`)

**Spec section:** "8. DischargePlanningRiskWorkflow" in the design doc.

**Per-workflow spec:**
- Request fields (all `str`): `patient_summary`, `hospitalization_summary`, `proposed_discharge_plan`, `social_determinants`, `readmission_history`, `care_team_notes`
- Flag headers: `READMISSION FLAGS:`, `CARE-GAP FLAGS:`, `SOCIAL-DETERMINANT FLAGS:`
- Score threshold: 7.5
- Checklist owner: Discharge planner / Social worker / Care coordinator
- Reviewer criteria: 5 dimensions — READMISSION-RISK (30%), CARE-GAP IDENTIFICATION (25%), SOCIAL-DETERMINANT ATTENTION (20%), PLAN ACTIONABILITY (15%), CARE-TEAM ALIGNMENT (10%)

**Structural template:** Follow Task 2 exactly. Substitutions:
- Module docstring: workflow purpose = 30-day readmission risk + care gap identification for the discharge planner
- `_DISCLAIMER`: "ADVISORY ONLY — This AI-generated discharge plan is not an order set. A discharge planner / social worker must verify social-determinant context and confirm post-acute placement, follow-up appointments, and medication reconciliation before discharge. AI output must never replace clinical or care-coordination judgement."
- `_DISCHARGE_REVIEW_CRITERIA`: 5 dimensions named above; flag headers as listed
- `_INITIAL_PROMPT`: section names = `## Readmission risk`, `## Care gaps`, `## Social-determinant context`, `## Discharge plan revisions`, `## Claims`
- `_FLAG_HEADERS = ("READMISSION FLAGS:", "CARE-GAP FLAGS:", "SOCIAL-DETERMINANT FLAGS:")`
- Banner dict in `_format_flag_section`:
  - `READMISSION FLAGS:` → "tighten or escalate post-acute follow-up; LACE/HOSPITAL-equivalent rationale required"
  - `CARE-GAP FLAGS:` → "name the missing service or referral; do not assume hand-off"
  - `SOCIAL-DETERMINANT FLAGS:` → "address transportation, housing, food security, or insurance barriers; AI must not assume they resolve themselves"
- Metadata keys: `readmission_flags`, `care_gap_flags`, `social_determinant_flags`, `discharge_checklist`
- Checklist owner: `[OWNER: Discharge Planner / Social Worker / Care Coordinator]`
- Checklist items:
  - "Confirm post-acute placement (SNF/IRF/LTACH/home) bed availability and authorization"
  - "Verify follow-up appointments are scheduled with primary care + specialist within 7 days"
  - "Complete medication reconciliation and confirm patient understanding of changes"
  - "Address every SOCIAL-DETERMINANT flag with a named referral or resource"
  - "Document discharge readiness sign-off in care management system"

**PRODUCTION_GAPS (in workflow docstring):**
1. PHI de-identification — caller responsibility
2. EHR integration — Epic/Cerner discharge module
3. Real-time bed availability — SNF/IRF/LTACH placement APIs
4. Payer authorization — post-acute service prior auth
5. Readmission risk model — production should use validated model (LACE, HOSPITAL); LLM provides contextual adjustment, not baseline
6. Dedicated SDOH auditor — third-model audit for social-determinant attention bias

- [ ] **Step 1: Write the failing test file**

Use the same test structure as Task 2 `tests/unit/test_diagnosis_code_audit.py`, but:
- Replace request fixture fields with `patient_summary`, `hospitalization_summary`, `proposed_discharge_plan`, `social_determinants`, `readmission_history`, `care_team_notes` (synthetic 65yo CHF readmission scenario)
- Replace flag header strings in critique fixtures with `READMISSION FLAGS:`, `CARE-GAP FLAGS:`, `SOCIAL-DETERMINANT FLAGS:`
- Replace metadata key assertions with `readmission_flags`, `care_gap_flags`, `social_determinant_flags`, `discharge_checklist`
- Test class names: `TestRequestToPromptText`, `TestConvergence` (3 cases), `TestMetadata`, `TestDisclaimer`
- 7 tests total

- [ ] **Step 2: Run test — verify ImportError**

```bash
python -m pytest tests/unit/test_discharge_planning_risk.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement the workflow**

Create `src/adv_multi_agent/healthcare/workflows/discharge_planning_risk.py` using Task 2's full code as the structural template. Apply every substitution listed in the per-workflow spec above. The `to_prompt_text` body:
```python
def to_prompt_text(self) -> str:
    cap = _MAX_FIELD_CHARS
    return "\n".join([
        f"Patient summary: {self.patient_summary[:cap]}",
        f"Hospitalization summary: {self.hospitalization_summary[:cap]}",
        f"Proposed discharge plan: {self.proposed_discharge_plan[:cap]}",
        f"Social determinants: {self.social_determinants[:cap]}",
        f"Readmission history: {self.readmission_history[:cap]}",
        f"Care team notes: {self.care_team_notes[:cap]}",
    ])
```

- [ ] **Step 4: Run the test — verify it passes**

```bash
python -m pytest tests/unit/test_discharge_planning_risk.py -v
```
Expected: all 7 tests pass.

- [ ] **Step 5: Run mypy + ruff**

```bash
python -m mypy src/adv_multi_agent/healthcare/workflows/discharge_planning_risk.py --strict
python -m ruff check src/adv_multi_agent/healthcare/workflows/discharge_planning_risk.py
```
Expected: clean.

- [ ] **Step 6: Create the 4 skill templates**

Follow Task 2's template structure. Templates:
- `discharge_initial.md` — section names: `## Readmission risk`, `## Care gaps`, `## Social-determinant context`, `## Discharge plan revisions`, `## Claims`. Inputs: `patient_summary`, `hospitalization_summary`, `proposed_discharge_plan`, `social_determinants`, `readmission_history`, `care_team_notes`.
- `discharge_revision.md` — same as Task 2 revision template; instruction: "for every flagged item, name the specific referral, appointment, or resource; do not assume."
- `discharge_review.md` — 5 reviewer dimensions, flag headers as listed.
- `discharge_checklist.md` — owner + 5 checklist items per spec.

- [ ] **Step 7: Create the example script**

`examples/healthcare/discharge_planning_risk.py` — same structure as Task 2 example. Synthetic scenario: 78yo woman, CHF exacerbation, prior 30-day readmission, lives alone, food-security concern, no transportation for follow-up.

- [ ] **Step 8: Run full test suite**

```bash
python -m pytest tests/ -q && python -m mypy src/ --strict && python -m ruff check src/
```
Expected: 495 passed (488 + 7 new), mypy + ruff clean.

- [ ] **Step 9: Commit**

```bash
git add src/adv_multi_agent/healthcare/workflows/discharge_planning_risk.py \
        src/adv_multi_agent/healthcare/skills/templates/discharge_*.md \
        tests/unit/test_discharge_planning_risk.py \
        examples/healthcare/discharge_planning_risk.py
git commit -m "feat(healthcare): DischargePlanningRiskWorkflow (READMISSION + CARE-GAP + SOCIAL-DETERMINANT flags)"
```

---

## Task 4: Implement `PriorAuthorizationReviewWorkflow` (non-veto)

**Files:**
- Create: `src/adv_multi_agent/healthcare/workflows/prior_authorization_review.py`
- Create: `tests/unit/test_prior_authorization_review.py`
- Create: `examples/healthcare/prior_authorization_review.py`
- Create: 4 skill templates (`prior_auth_*.md`)

**Spec section:** "5. PriorAuthorizationReviewWorkflow" in design doc.

**Per-workflow spec:**
- Request fields (all `str`): `member_id`, `requested_service`, `clinical_rationale`, `diagnosis_codes`, `clinical_guidelines`, `member_history`, `alternatives_tried`
- Flag headers: `MEDICAL-NECESSITY FLAGS:`, `COVERAGE FLAGS:`, `DOCUMENTATION FLAGS:`
- Score threshold: 7.5
- Checklist owner: Prior auth nurse / case manager
- Reviewer criteria: 5 dimensions — MEDICAL-NECESSITY GROUNDING (30%), COVERAGE-POLICY FIT (25%), DOCUMENTATION SUFFICIENCY (20%), STEP-THERAPY VERIFICATION (15%), DECISION CLARITY (10%)

**Structural template:** Task 2. Substitutions:
- `_DISCLAIMER`: "ADVISORY ONLY — This AI-generated prior auth review is not a coverage determination. A licensed nurse reviewer or medical director must verify medical necessity against the payer's coverage policy before issuing any approval or denial. AI output must never auto-approve or auto-deny."
- Reviewer criteria flag headers as listed
- `_INITIAL_PROMPT` sections: `## Medical-necessity assessment`, `## Coverage-policy fit`, `## Documentation review`, `## Step-therapy verification`, `## Recommendation`, `## Claims`
- `_FLAG_HEADERS = ("MEDICAL-NECESSITY FLAGS:", "COVERAGE FLAGS:", "DOCUMENTATION FLAGS:")`
- Banner dict:
  - `MEDICAL-NECESSITY FLAGS:` → "ground every medical-necessity claim in the clinical guideline; do not paraphrase from general practice"
  - `COVERAGE FLAGS:` → "cite the specific coverage policy section; if outside policy, recommend medical-director review or peer-to-peer"
  - `DOCUMENTATION FLAGS:` → "name the missing documentation specifically; request rather than approve without"
- Metadata: `medical_necessity_flags`, `coverage_flags`, `documentation_flags`, `prior_auth_checklist`
- Checklist owner: `[OWNER: Prior Authorization Nurse / Case Manager]`
- Checklist items:
  - "Confirm member eligibility and benefit at the date of service requested"
  - "Verify cited clinical guideline (InterQual / MCG) effective version"
  - "Document medical-necessity rationale citing specific guideline criteria"
  - "Route denials to medical director for physician review before issuance"
  - "Notify provider of decision within plan turnaround time (urgent 72h / standard 5 business days)"

**PRODUCTION_GAPS:**
1. PHI de-identification
2. Real-time eligibility (payer claims system)
3. InterQual / MCG integration
4. PA system integration (Cohere, AIM, etc.)
5. Peer-to-peer review gate — denials require physician review
6. Dedicated third-model bias auditor — for parity-protected-class detection

- [ ] **Step 1: Write the failing test file**

Test structure same as Task 2. Synthetic request fixture: requested high-cost specialty drug, diagnosis codes, prior step therapy. 7 tests covering Request rendering, convergence (clean / flag-blocked / flag-cleared), metadata, disclaimer.

- [ ] **Step 2: Run test — verify ImportError**

```bash
python -m pytest tests/unit/test_prior_authorization_review.py -v
```

- [ ] **Step 3: Implement the workflow**

Full file mirroring Task 2 with the substitutions above. `to_prompt_text`:
```python
def to_prompt_text(self) -> str:
    cap = _MAX_FIELD_CHARS
    return "\n".join([
        f"Member ID: {self.member_id[:cap]}",
        f"Requested service: {self.requested_service[:cap]}",
        f"Clinical rationale: {self.clinical_rationale[:cap]}",
        f"Diagnosis codes: {self.diagnosis_codes[:cap]}",
        f"Clinical guidelines: {self.clinical_guidelines[:cap]}",
        f"Member history: {self.member_history[:cap]}",
        f"Alternatives tried: {self.alternatives_tried[:cap]}",
    ])
```

- [ ] **Step 4-9:** Run test (verify pass), mypy + ruff (verify clean), create 4 skill templates (`prior_auth_initial.md`, `prior_auth_revision.md`, `prior_auth_review.md`, `prior_auth_checklist.md`), create example (synthetic specialty drug PA request scenario), run full suite (502 passed), commit:

```bash
git add src/adv_multi_agent/healthcare/workflows/prior_authorization_review.py \
        src/adv_multi_agent/healthcare/skills/templates/prior_auth_*.md \
        tests/unit/test_prior_authorization_review.py \
        examples/healthcare/prior_authorization_review.py
git commit -m "feat(healthcare): PriorAuthorizationReviewWorkflow (MEDICAL-NECESSITY + COVERAGE + DOCUMENTATION flags)"
```

---

## Task 5: Implement `ClaimsAppealReviewWorkflow` (non-veto)

**Files:**
- Create: `src/adv_multi_agent/healthcare/workflows/claims_appeal_review.py`
- Create: `tests/unit/test_claims_appeal_review.py`
- Create: `examples/healthcare/claims_appeal_review.py`
- Create: 4 skill templates (`claims_appeal_*.md`)

**Spec section:** "6. ClaimsAppealReviewWorkflow" in design doc.

**Per-workflow spec:**
- Request fields (all `str`): `claim_id`, `denied_service`, `appeal_narrative`, `clinical_evidence`, `coverage_policy`, `original_review_summary`, `treating_physician_statement`
- Flag headers: `EVIDENCE FLAGS:`, `COVERAGE FLAGS:`, `PROCEDURE FLAGS:`
- Score threshold: 7.5
- Checklist owner: Appeals coordinator / Medical director
- Reviewer criteria: 5 dimensions — EVIDENCE STRENGTH (30%), COVERAGE-POLICY ALIGNMENT (25%), PROCEDURAL COMPLIANCE (20%), CONSISTENCY WITH ORIGINAL DENIAL (15%), DECISION CLARITY (10%)

**Structural template:** Task 2 with substitutions. `_DISCLAIMER`: "ADVISORY ONLY — This AI-generated appeal review is not an overturn or uphold determination. A medical director (for first-level clinical appeals) or external review organization (for second-level) must independently render the decision."

Banner dict:
- `EVIDENCE FLAGS:` → "address the specific clinical evidence — labs, imaging, treatment failure — that supports or contradicts the original denial"
- `COVERAGE FLAGS:` → "cite the effective-date-versioned coverage policy; do not interpret beyond plain language"
- `PROCEDURE FLAGS:` → "verify appeal timeline (72h urgent, 30 days standard ERISA) and required notifications"

Metadata keys: `evidence_flags`, `coverage_flags`, `procedure_flags`, `appeal_checklist`.

Checklist: "[OWNER: Appeals Coordinator / Medical Director]"; items: confirm timeline; verify policy version effective at DOS; route to medical director if clinical; notify member of decision with appeal rights; document rationale.

PRODUCTION_GAPS: PHI de-identification; claims system integration; coverage policy version control; medical director sign-off gate; ERISA / state appeal timeline tracking.

**`to_prompt_text`:**
```python
def to_prompt_text(self) -> str:
    cap = _MAX_FIELD_CHARS
    return "\n".join([
        f"Claim ID: {self.claim_id[:cap]}",
        f"Denied service: {self.denied_service[:cap]}",
        f"Appeal narrative: {self.appeal_narrative[:cap]}",
        f"Clinical evidence: {self.clinical_evidence[:cap]}",
        f"Coverage policy: {self.coverage_policy[:cap]}",
        f"Original review summary: {self.original_review_summary[:cap]}",
        f"Treating physician statement: {self.treating_physician_statement[:cap]}",
    ])
```

- [ ] **Step 1-9:** Follow Task 2 sequence: write failing test (7 tests, mirror Task 2 structure with claims-appeal field names + flag headers), verify ImportError, implement workflow with substitutions above, verify tests pass, mypy + ruff clean, create 4 skill templates, create example (synthetic denial appeal scenario), run full suite (509 passed), commit:

```bash
git add src/adv_multi_agent/healthcare/workflows/claims_appeal_review.py \
        src/adv_multi_agent/healthcare/skills/templates/claims_appeal_*.md \
        tests/unit/test_claims_appeal_review.py \
        examples/healthcare/claims_appeal_review.py
git commit -m "feat(healthcare): ClaimsAppealReviewWorkflow (EVIDENCE + COVERAGE + PROCEDURE flags)"
```

---

## Task 6: Implement `DrugInteractionFlaggingWorkflow` (worked example — veto)

**Files:**
- Create: `src/adv_multi_agent/healthcare/workflows/drug_interaction_flagging.py`
- Create: `tests/unit/test_drug_interaction_flagging.py`
- Create: `examples/healthcare/drug_interaction_flagging.py`
- Create: 4 skill templates (`drug_initial.md`, `drug_revision.md`, `drug_review.md`, `drug_checklist.md`)

**Spec section:** "3. DrugInteractionFlaggingWorkflow" in design doc.

**Per-workflow spec:**
- Request fields (all `str`): `patient_id`, `medication_list`, `new_medication`, `indication`, `renal_function`, `hepatic_function`, `allergy_history`, `formulary_reference`
- Flag headers: `SEVERITY FLAGS:`, `EVIDENCE FLAGS:`, `CONTRAINDICATION FLAGS:`
- Score threshold: **8.0** (veto-class)
- VETO triggers (verbatim from design spec, included in reviewer criteria):
  - Absolute contraindication between new_medication and any drug in medication_list (per formulary or standard reference)
  - QTc-prolonging combination in patient with documented cardiac history or prolonged baseline QTc
  - Narrow-therapeutic-index interaction (warfarin + NSAID, lithium + thiazide, etc.) with no dose adjustment plan
  - Cross-allergy with documented allergy in allergy_history
- Checklist owner: Clinical pharmacist
- Reviewer criteria: 5 dimensions — SEVERITY ASSESSMENT (30%), EVIDENCE-BASE CITATION (25%), CONTRAINDICATION COMPLETENESS (20%), ORGAN-FUNCTION DOSING (15%), ACTIONABILITY (10%)

**Reference structure:** `src/adv_multi_agent/industrial/workflows/product_liability_root_cause.py` (triple-flag + veto). Read it first. Key elements unique to veto workflows:
- Import `extract_veto_directive` from `core._internal`
- `_extract_veto` static method delegates to `extract_veto_directive(critique, "REVIEWER VETO:", max_chars)`
- Loop has `veto_reason = self._extract_veto(review.critique, max_wiki_chars); if veto_reason is not None: break` AFTER `wiki.add_feedback` (audit-trail-before-veto-break)
- `_compose_output(output, veto_reason)` prepends a VETO banner when vetoed
- Metadata adds `veto_reason`, `vetoed`, `first_draft` (L-IND-2 — captures clean executor draft from vetoed round)
- Reviewer criteria template ends with FORMAT NOTE (L-PC-2) and VETO CRITERIA block
- Reviewer criteria template includes verbatim list of veto triggers from spec
- `_DISCLAIMER` for vetoed path: "REVIEWER VETO — workflow halted before convergence. The reviewer identified a life-safety / regulatory condition that requires human escalation BEFORE any further automation. See metadata['veto_reason']. Escalate to <role>."

- [ ] **Step 1: Write the failing test file**

Create `tests/unit/test_drug_interaction_flagging.py` mirroring `tests/unit/test_product_liability_root_cause.py`:
```python
"""Unit tests for DrugInteractionFlaggingWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.healthcare.workflows.drug_interaction_flagging import (
    DrugInteractionFlaggingWorkflow,
    DrugInteractionRequest,
    _DISCLAIMER,
    _MAX_FIELD_CHARS,
)
from .fakes import FakeExecutor, FakeReviewer


def make_config(tmp_path: Path, **kwargs: Any) -> Config:
    defaults: dict[str, Any] = dict(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=3,
        score_threshold=8.0,
    )
    defaults.update(kwargs)
    return Config(**defaults)


def make_review(
    score: float, *, approved: bool, critique: str = "",
    suggestions: list[str] | None = None,
) -> ReviewResult:
    return ReviewResult(
        score=score, critique=critique,
        suggestions=suggestions or [], approved=approved,
    )


def make_request(**kwargs: Any) -> DrugInteractionRequest:
    defaults: dict[str, Any] = dict(
        patient_id="PT-2026-04812",
        medication_list="warfarin 5mg daily; metoprolol 50mg BID; lisinopril 10mg daily",
        new_medication="ibuprofen 600mg q6h prn (proposed for OA flare)",
        indication="osteoarthritis pain flare, NSAID requested by patient",
        renal_function="eGFR 58 mL/min/1.73m² (CKD3a)",
        hepatic_function="LFTs WNL; no cirrhosis",
        allergy_history="no documented drug allergies",
        formulary_reference="Lexicomp interaction monograph: warfarin + NSAID = major; "
                            "INR + bleeding risk increase 3-7 fold",
    )
    defaults.update(kwargs)
    return DrugInteractionRequest(**defaults)


def clean_critique() -> str:
    return (
        "SEVERITY FLAGS: None detected\n"
        "EVIDENCE FLAGS: None detected\n"
        "CONTRAINDICATION FLAGS: None detected\n"
        "REVIEWER VETO: None"
    )


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        assert "Patient ID:" in text
        assert "Medication list:" in text
        assert "New medication:" in text
        assert "Indication:" in text
        assert "Renal function:" in text
        assert "Hepatic function:" in text
        assert "Allergy history:" in text
        assert "Formulary reference:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(formulary_reference=oversized).to_prompt_text()
        formulary_section = text.split("Formulary reference:")[1].split("\n")[0]
        assert len(formulary_section.strip()) <= _MAX_FIELD_CHARS + 5


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(outputs=["## Interaction analysis\n..."])
        reviewer = FakeReviewer(results=[
            make_review(8.5, approved=True, critique=clean_critique())
        ])
        wf = DrugInteractionFlaggingWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert "vetoed" not in result.metadata
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_with_severity_flag(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(outputs=["d1", "d2", "d3"])
        critique = (
            "SEVERITY FLAGS:\n  - warfarin + NSAID major interaction\n"
            "EVIDENCE FLAGS: None detected\n"
            "CONTRAINDICATION FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer(results=[
            make_review(8.5, approved=True, critique=critique),
            make_review(8.5, approved=True, critique=critique),
            make_review(8.5, approved=True, critique=critique),
        ])
        wf = DrugInteractionFlaggingWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(outputs=["initial draft"])
        critique = (
            "SEVERITY FLAGS: None detected\n"
            "EVIDENCE FLAGS: None detected\n"
            "CONTRAINDICATION FLAGS: None detected\n"
            "REVIEWER VETO: Absolute contraindication — warfarin + NSAID at this "
            "eGFR is bleeding-risk-class; escalate to pharmacist before any dose."
        )
        reviewer = FakeReviewer(results=[
            make_review(7.0, approved=False, critique=critique)
        ])
        wf = DrugInteractionFlaggingWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert result.metadata["vetoed"] is True
        assert "Absolute contraindication" in result.metadata["veto_reason"]
        assert "REVIEWER VETO" in result.output
        assert result.metadata["first_draft"] == "initial draft"

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(outputs=["draft"])
        reviewer = FakeReviewer(results=[
            make_review(8.5, approved=True, critique=clean_critique())
        ])
        wf = DrugInteractionFlaggingWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert "veto_reason" not in result.metadata
        assert "vetoed" not in result.metadata


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(outputs=["draft"])
        reviewer = FakeReviewer(results=[
            make_review(8.5, approved=True, critique=clean_critique())
        ])
        wf = DrugInteractionFlaggingWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert "severity_flags" in result.metadata
        assert "evidence_flags" in result.metadata
        assert "contraindication_flags" in result.metadata
        assert "interaction_checklist" in result.metadata
        assert "ledger_summary" in result.metadata
```

- [ ] **Step 2: Run test — verify ImportError**

```bash
python -m pytest tests/unit/test_drug_interaction_flagging.py -v
```

- [ ] **Step 3: Implement the workflow**

Create `src/adv_multi_agent/healthcare/workflows/drug_interaction_flagging.py` following the full structure of `src/adv_multi_agent/industrial/workflows/product_liability_root_cause.py`. The complete file must include:

Module docstring with PRODUCTION_GAPS:
1. PHI de-identification
2. Live interaction database (Lexicomp / Micromedex / First Datacheck)
3. EHR medication reconciliation
4. Pharmacist order verification gate
5. Renal/hepatic dosing calculator (validated)
6. Dedicated third-model interaction auditor

Imports:
```python
from ...core._internal import (
    extract_flags,
    extract_veto_directive,
    sanitize_for_prompt,
    truncate_flag_display,
)
from ...core.workflow import BaseWorkflow, WorkflowResult
```

Constants:
```python
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated drug-interaction review is not "
    "a pharmacist verification. A licensed clinical pharmacist must "
    "independently verify every flagged interaction against the live "
    "formulary / interaction database (Lexicomp, Micromedex) before any "
    "medication is dispensed or administered. AI output must never trigger "
    "automated prescribing or dispensing."
)

_VETO_BANNER = (
    "⚠️  REVIEWER VETO — workflow halted before convergence. The reviewer "
    "identified a drug-interaction condition that requires immediate "
    "clinical-pharmacist escalation BEFORE any prescribing decision. "
    "See metadata['veto_reason']. Escalate to clinical pharmacist."
)
```

Reviewer criteria template — include FORMAT NOTE + VETO CRITERIA block with verbatim veto trigger list:
```python
_DRUG_INTERACTION_REVIEW_CRITERIA = """\
Evaluate this drug-interaction analysis on five dimensions. Score each 0–10.

1. SEVERITY ASSESSMENT (30%) ...
2. EVIDENCE-BASE CITATION (25%) ...
3. CONTRAINDICATION COMPLETENESS (20%) ...
4. ORGAN-FUNCTION DOSING (15%) ...
5. ACTIONABILITY (10%) ...

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Absolute contraindication between new_medication and any drug in
    medication_list per formulary or standard interaction reference.
  • QTc-prolonging combination in patient with documented cardiac history
    or prolonged baseline QTc.
  • Narrow-therapeutic-index interaction (warfarin + NSAID, lithium +
    thiazide, etc.) without a documented dose-adjustment plan.
  • Cross-allergy with a documented allergy in allergy_history.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those
  as stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score ≥ 8.0 AND zero SEVERITY FLAGS AND zero EVIDENCE FLAGS AND zero
CONTRAINDICATION FLAGS AND no VETO: review ready for pharmacist sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SEVERITY FLAGS: [bullet list, or "None detected"]
  EVIDENCE FLAGS: [bullet list, or "None detected"]
  CONTRAINDICATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""
```

Initial/revision prompts: sections `## Interaction analysis`, `## Severity grading`, `## Contraindication check`, `## Dose-adjustment recommendation`, `## Claims`.

Request dataclass:
```python
@dataclass
class DrugInteractionRequest:
    """Structured input for the drug-interaction flagging workflow."""
    patient_id: str
    medication_list: str
    new_medication: str
    indication: str
    renal_function: str
    hepatic_function: str
    allergy_history: str
    formulary_reference: str

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Patient ID: {self.patient_id[:cap]}",
            f"Medication list: {self.medication_list[:cap]}",
            f"New medication: {self.new_medication[:cap]}",
            f"Indication: {self.indication[:cap]}",
            f"Renal function: {self.renal_function[:cap]}",
            f"Hepatic function: {self.hepatic_function[:cap]}",
            f"Allergy history: {self.allergy_history[:cap]}",
            f"Formulary reference: {self.formulary_reference[:cap]}",
        ])

_FLAG_HEADERS: tuple[str, ...] = (
    "SEVERITY FLAGS:",
    "EVIDENCE FLAGS:",
    "CONTRAINDICATION FLAGS:",
)
```

Workflow `run` method — mirror `product_liability_root_cause.py` exactly:
- Initialize `current` / `accumulated` dicts keyed by `_FLAG_HEADERS`
- `veto_reason: str | None = None`
- Loop `for round_num in range(1, config.max_review_rounds + 1)`:
  - Format prompt (initial vs revision with `_format_flag_section`)
  - `output = await self.executor.run(prompt, context="")`
  - `self._register_claims(output, round_num)`
  - `review = await self.reviewer.review(output, criteria=_DRUG_INTERACTION_REVIEW_CRITERIA)`
  - `score = review.score`
  - Extract flags for each header into `current[header]`; extend `accumulated[header]`
  - `self.wiki.add_feedback(...)` BEFORE veto check (audit-trail-before-veto)
  - `veto_reason = self._extract_veto(review.critique, max_wiki_chars); if veto_reason is not None: break`
  - Else if `review.approved and not any(current.values()): converged = True; break`
- After loop:
  - `interaction_checklist = self._build_interaction_checklist(request, accumulated, veto_reason)`
  - `output_with_banner = self._compose_output(output, veto_reason)`
  - Build metadata dict with `severity_flags`, `evidence_flags`, `contraindication_flags`, `interaction_checklist`, `disclaimer`, `ledger_summary`
  - If `veto_reason is not None`: add `veto_reason`, `vetoed=True`, `first_draft=output` (L-IND-2)
  - Return `WorkflowResult`

Static methods:
- `_extract_veto(critique, max_chars) -> str | None`: delegate to `extract_veto_directive(critique, "REVIEWER VETO:", max_chars)`
- `_format_flag_section(current)`: banners — `SEVERITY FLAGS:` "narrow severity to formulary reference", `EVIDENCE FLAGS:` "cite the specific monograph or guideline; do not paraphrase severity", `CONTRAINDICATION FLAGS:` "name the contraindicating drug pair or allergy mechanism"
- `_compose_output(draft, veto_reason)`:
```python
@staticmethod
def _compose_output(draft: str, veto_reason: str | None) -> str:
    if veto_reason is None:
        return f"{draft}\n\n---\n\n{_DISCLAIMER}"
    return (
        f"{_VETO_BANNER}\n\nVETO DIRECTIVE: {veto_reason}\n\n"
        f"--- Vetoed draft below ---\n\n{draft}\n\n---\n\n{_DISCLAIMER}"
    )
```
- `_build_interaction_checklist(request, accumulated, veto_reason)`: owner = "[OWNER: Clinical Pharmacist]"; items:
  - "[ ] 🛑 REVIEWER VETO — escalate to clinical pharmacist BEFORE any prescribing action" (only if veto)
  - Per-flag-class lines if flags present
  - "[ ] Verify every flagged interaction against live Lexicomp / Micromedex monograph"
  - "[ ] Confirm renal / hepatic dose adjustments against validated calculator"
  - "[ ] Pharmacist sign-off in EHR before dispensing"

- [ ] **Step 4: Run the test — verify it passes**

```bash
python -m pytest tests/unit/test_drug_interaction_flagging.py -v
```
Expected: all 8 tests pass (including 2 veto tests).

- [ ] **Step 5: Run mypy + ruff**

```bash
python -m mypy src/adv_multi_agent/healthcare/workflows/drug_interaction_flagging.py --strict
python -m ruff check src/adv_multi_agent/healthcare/workflows/drug_interaction_flagging.py
```

- [ ] **Step 6: Create the 4 skill templates**

`drug_initial.md` — initial draft template; sections `## Interaction analysis`, `## Severity grading`, `## Contraindication check`, `## Dose-adjustment recommendation`, `## Claims`. Inputs: all 8 Request fields.

`drug_revision.md` — revise based on critique; instruction: "for every flagged interaction, cite the specific formulary monograph or interaction-reference entry; remove unsupported severity claims".

`drug_review.md` — 5 reviewer dimensions + VETO CRITERIA block with verbatim veto trigger list + FORMAT NOTE.

`drug_checklist.md` — owner = clinical pharmacist; veto-escalation row if vetoed; live formulary verification; pharmacist sign-off.

- [ ] **Step 7: Create the example script**

`examples/healthcare/drug_interaction_flagging.py` — synthetic scenario: 72yo CKD3 patient on warfarin + metoprolol + lisinopril, NSAID requested for OA. Demonstrates likely veto path on warfarin+NSAID.

- [ ] **Step 8: Run full suite**

```bash
python -m pytest tests/ -q && python -m mypy src/ --strict && python -m ruff check src/
```
Expected: 517 passed (509 + 8 new), mypy + ruff clean.

- [ ] **Step 9: Commit**

```bash
git add src/adv_multi_agent/healthcare/workflows/drug_interaction_flagging.py \
        src/adv_multi_agent/healthcare/skills/templates/drug_*.md \
        tests/unit/test_drug_interaction_flagging.py \
        examples/healthcare/drug_interaction_flagging.py
git commit -m "feat(healthcare): DrugInteractionFlaggingWorkflow (veto on absolute contraindication / QTc / NTI / cross-allergy)"
```

---

## Task 7: Implement `AdverseEventTriageWorkflow` (veto)

**Files:**
- Create: `src/adv_multi_agent/healthcare/workflows/adverse_event_triage.py`
- Create: `tests/unit/test_adverse_event_triage.py`
- Create: `examples/healthcare/adverse_event_triage.py`
- Create: 4 skill templates (`adverse_*.md`)

**Spec section:** "4. AdverseEventTriageWorkflow" in design doc.

**Per-workflow spec:**
- Request fields (all `str`): `product_name`, `event_description`, `patient_demographics`, `event_onset`, `causality_assessment`, `concomitant_medications`, `outcome`, `prior_reports`
- Flag headers: `SEVERITY FLAGS:`, `CAUSALITY FLAGS:`, `REGULATORY FLAGS:`
- Score threshold: **8.0**
- VETO triggers (verbatim):
  - Serious unexpected ADR (not in current product labeling per prior_reports) with causality ≥ possible → mandatory expedited report required
  - Fatal outcome with causality ≥ possible AND event not in current labeling → 7-day expedited reporting clock
  - Life-threatening outcome with causality ≥ probable → 7-day expedited reporting clock
- Checklist owner: Pharmacovigilance officer / drug safety scientist
- Reviewer criteria: 5 dimensions — SEVERITY GRADING (30%), CAUSALITY ASSESSMENT (25%), REGULATORY-OBLIGATION FIT (20%), MedDRA CODING ACCURACY (15%), ACTIONABILITY (10%)

**Structural template:** Task 6. Substitutions:
- D-HEALTH-4: VETO CRITERIA references **FDA 21 CFR 312 (IND safety report)** 7/15-day timelines and **ICH E2A** for serious / unexpected definitions — explicitly cite in the criteria template, not generic "safety concern" phrasing
- Banner dict:
  - `SEVERITY FLAGS:` → "grade severity against CTCAE / ICH E2A definitions; do not infer beyond reporter's narrative"
  - `CAUSALITY FLAGS:` → "use WHO-UMC or Naranjo causality scale; cite the specific criterion (temporal, dechallenge, rechallenge, alternative cause)"
  - `REGULATORY FLAGS:` → "match obligation to FDA 21 CFR 312 / EMA EudraVigilance / ICH E2A reporting clock (7-day for fatal+life-threatening unexpected; 15-day for other serious unexpected)"
- `_DISCLAIMER`: "ADVISORY ONLY — This AI-generated adverse-event triage is not a regulatory report. A qualified pharmacovigilance officer or drug-safety scientist must independently verify severity, causality, and labeling status, and file the MedWatch / EudraVigilance report. AI output must never substitute for qualified-physician causality assessment."
- `_VETO_BANNER`: "REVIEWER VETO — workflow halted before convergence. The reviewer identified a serious adverse event that triggers a mandatory expedited regulatory report. See metadata['veto_reason']. Escalate to pharmacovigilance officer; initiate MedWatch / EudraVigilance filing within the regulatory clock."
- Metadata keys: `severity_flags`, `causality_flags`, `regulatory_flags`, `adverse_event_checklist`
- Checklist owner: `[OWNER: Pharmacovigilance Officer / Drug Safety Scientist]`
- Checklist items (veto path adds escalation rows):
  - "[ ] 🛑 REVIEWER VETO — initiate MedWatch / EudraVigilance expedited filing within regulatory clock" (veto only)
  - "[ ] Verify MedDRA PT/SOC coding for event_description"
  - "[ ] Confirm causality assessment via WHO-UMC or Naranjo with documented criteria"
  - "[ ] Confirm labeling status against current USPI / SmPC / sponsor safety database"
  - "[ ] Notify sponsor / SUSAR-relevant parties per ICH E2A if clinical trial"
  - "[ ] File final report and document in safety database"

**PRODUCTION_GAPS:**
1. PHI de-identification
2. Safety database integration (FAERS, EudraVigilance, sponsor safety DB)
3. MedWatch / EudraVigilance filing automation — output is advisory
4. MedDRA coding validation — qualified medical coder required
5. Sponsor SUSAR notification automation (ICH E2A)
6. Dedicated third-model causality auditor

- [ ] **Step 1-9:** Follow Task 6 sequence:
1. Write failing test (8 tests: Request rendering, convergence clean / blocked, veto halts loop + first_draft preserved, no-veto when None, metadata)
2. Verify ImportError
3. Implement workflow mirroring Task 6 with substitutions above; reviewer criteria includes FDA 21 CFR 312 + ICH E2A citation language (D-HEALTH-4)
4. Verify tests pass
5. mypy + ruff clean
6. Create 4 skill templates (`adverse_initial.md`, `adverse_revision.md`, `adverse_review.md`, `adverse_checklist.md`)
7. Create example: synthetic fatal anaphylaxis after antibiotic; expected veto path on "fatal + causality probable + unexpected"
8. Run full suite — 525 passed (517 + 8)
9. Commit:

```bash
git add src/adv_multi_agent/healthcare/workflows/adverse_event_triage.py \
        src/adv_multi_agent/healthcare/skills/templates/adverse_*.md \
        tests/unit/test_adverse_event_triage.py \
        examples/healthcare/adverse_event_triage.py
git commit -m "feat(healthcare): AdverseEventTriageWorkflow (veto on serious-unexpected ADR triggering FDA/EMA expedited report)"
```

---

## Task 8: Implement `TreatmentPlanReviewWorkflow` (veto)

**Files:**
- Create: `src/adv_multi_agent/healthcare/workflows/treatment_plan_review.py`
- Create: `tests/unit/test_treatment_plan_review.py`
- Create: `examples/healthcare/treatment_plan_review.py`
- Create: 4 skill templates (`treatment_*.md`)

**Spec section:** "2. TreatmentPlanReviewWorkflow" in design doc.

**Per-workflow spec:**
- Request fields (all `str`): `patient_summary`, `proposed_plan`, `current_medications`, `lab_values`, `clinical_guidelines`, `contraindication_context`
- Flag headers: `GUIDELINE FLAGS:`, `CONTRAINDICATION FLAGS:`, `RISK FLAGS:`
- Score threshold: **8.0**
- VETO triggers:
  - Absolute drug-allergy contraindication present in patient_summary or contraindication_context
  - Drug-organ-failure contraindication (renally-cleared drug at full dose with eGFR < threshold per guidelines)
  - Procedure listed in proposed_plan is contraindicated given documented comorbidity or medication
- Checklist owner: Attending physician
- Reviewer criteria: 5 dimensions — GUIDELINE GROUNDING (30%), CONTRAINDICATION COMPLETENESS (25%), RISK STRATIFICATION (20%), DOSE/ROUTE/DURATION SPECIFICITY (15%), ACTIONABILITY (10%)

**Structural template:** Task 6. Substitutions:
- `_DISCLAIMER`: "ADVISORY ONLY — This AI-generated treatment-plan review is not a prescription or order set. An attending physician must independently verify guideline grounding, contraindication completeness, and risk against the patient's full record before any order entry. AI output must never trigger automated prescribing or procedural scheduling."
- `_VETO_BANNER`: "REVIEWER VETO — workflow halted. The reviewer identified an absolute contraindication that requires physician escalation BEFORE any prescribing decision. See metadata['veto_reason']. Escalate to attending physician."
- Banner dict:
  - `GUIDELINE FLAGS:` → "ground every clinical claim in the cited guideline; cite section, not summary"
  - `CONTRAINDICATION FLAGS:` → "name the specific contraindication mechanism (drug-allergy, drug-organ, drug-condition)"
  - `RISK FLAGS:` → "stratify risk against patient-specific factors (age, comorbidity, lab values); do not import baseline-population risk"
- Metadata keys: `guideline_flags`, `contraindication_flags`, `risk_flags`, `treatment_checklist`
- Checklist owner: `[OWNER: Attending Physician]`
- Checklist items: physician review of every flag; medication reconciliation; pharmacy verification for new orders; documentation of risk discussion; order entry only after sign-off

**`to_prompt_text`:**
```python
def to_prompt_text(self) -> str:
    cap = _MAX_FIELD_CHARS
    return "\n".join([
        f"Patient summary: {self.patient_summary[:cap]}",
        f"Proposed plan: {self.proposed_plan[:cap]}",
        f"Current medications: {self.current_medications[:cap]}",
        f"Lab values: {self.lab_values[:cap]}",
        f"Clinical guidelines: {self.clinical_guidelines[:cap]}",
        f"Contraindication context: {self.contraindication_context[:cap]}",
    ])
```

PRODUCTION_GAPS: PHI; EHR integration; live drug knowledge base; physician sign-off gate; pharmacy verification.

- [ ] **Step 1-9:** Follow Task 6 sequence: 8 tests, full implementation mirroring Task 6, 4 templates, example (synthetic 70yo CHF + CKD3 patient with proposed contrast-enhanced procedure → veto on contrast nephropathy contraindication), run suite (533 passed), commit:

```bash
git add src/adv_multi_agent/healthcare/workflows/treatment_plan_review.py \
        src/adv_multi_agent/healthcare/skills/templates/treatment_*.md \
        tests/unit/test_treatment_plan_review.py \
        examples/healthcare/treatment_plan_review.py
git commit -m "feat(healthcare): TreatmentPlanReviewWorkflow (veto on absolute drug-allergy / drug-organ / procedure contraindication)"
```

---

## Task 9: Implement `ClinicalTrialEligibilityWorkflow` (veto + bias-gate)

**Files:**
- Create: `src/adv_multi_agent/healthcare/workflows/clinical_trial_eligibility.py`
- Create: `tests/unit/test_clinical_trial_eligibility.py`
- Create: `examples/healthcare/clinical_trial_eligibility.py`
- Create: 4 skill templates (`trial_*.md`)

**Spec section:** "1. ClinicalTrialEligibilityWorkflow" in design doc.

**Per-workflow spec:**
- Request fields (all `str`): `trial_id`, `protocol_summary`, `patient_profile`, `biomarker_status`, `prior_treatments`, `competing_risks`, `site_context`
- Flag headers: `BIAS FLAGS:`, `ELIGIBILITY FLAGS:`, `EVIDENCE FLAGS:`
- Score threshold: **8.0**
- VETO triggers:
  - Patient meets a life-threatening exclusion criterion (organ dysfunction, prohibited concomitant med, active infection per protocol) but draft marks eligible
  - Protected-class attribute (race, sex, age, disability) appears to be a determinative exclusion factor without protocol-specified clinical justification
  - Eligibility determination contradicts primary evidence in protocol_summary or biomarker_status
- Checklist owner: IRB coordinator / principal investigator
- Reviewer criteria: 5 dimensions — PROTOCOL FIDELITY (30%), BIAS DETECTION (25%) [parole-pattern bias-gate], EVIDENCE GROUNDING (20%), SAFETY EXCLUSION COMPLETENESS (15%), DECISION CLARITY (10%)

**Structural template:** Task 6. Substitutions:
- Reviewer criteria includes a dedicated BIAS DETECTION dimension referencing parole-pattern (D-HEALTH-4: cite specific demographic-bias literature in the criteria template — e.g. "trial enrollment under-represents racial/ethnic minorities and women in cardiology RCTs per JAMA 2019 systematic review")
- `_DISCLAIMER`: "ADVISORY ONLY — This AI-generated trial-eligibility assessment is not an enrollment decision. The principal investigator must independently verify every exclusion criterion against the protocol and the patient's full EHR before enrollment. The IRB coordinator must confirm bias detection findings against site enrollment statistics. AI output must never auto-enroll or auto-exclude."
- `_VETO_BANNER`: "REVIEWER VETO — workflow halted. The reviewer identified a life-safety eligibility issue OR a protected-class bias signal. See metadata['veto_reason']. Escalate to PI and IRB coordinator."
- Banner dict:
  - `BIAS FLAGS:` → "remove protected-class attribute from determinative role; document clinical justification per protocol"
  - `ELIGIBILITY FLAGS:` → "re-verify every criterion against the protocol section number"
  - `EVIDENCE FLAGS:` → "cite the biomarker / lab / treatment-history input directly; do not paraphrase eligibility"
- Metadata keys: `bias_flags`, `eligibility_flags`, `evidence_flags`, `trial_checklist`
- Checklist owner: `[OWNER: IRB Coordinator / Principal Investigator]`
- Checklist items (veto path adds bias-escalation):
  - "[ ] 🛑 REVIEWER VETO — escalate to PI + IRB coordinator BEFORE any enrollment action" (veto only)
  - "[ ] Verify every exclusion criterion against protocol section number"
  - "[ ] Confirm biomarker status from primary lab report, not free-text summary"
  - "[ ] If BIAS FLAGS present, document clinical justification per protocol AND review site enrollment statistics for under-representation"
  - "[ ] IRB and PI joint sign-off before enrollment"

**`to_prompt_text`:**
```python
def to_prompt_text(self) -> str:
    cap = _MAX_FIELD_CHARS
    return "\n".join([
        f"Trial ID: {self.trial_id[:cap]}",
        f"Protocol summary: {self.protocol_summary[:cap]}",
        f"Patient profile: {self.patient_profile[:cap]}",
        f"Biomarker status: {self.biomarker_status[:cap]}",
        f"Prior treatments: {self.prior_treatments[:cap]}",
        f"Competing risks: {self.competing_risks[:cap]}",
        f"Site context: {self.site_context[:cap]}",
    ])
```

PRODUCTION_GAPS: PHI de-identification (EHR Safe Harbor pipeline); live protocol database (ClinicalTrials.gov, sponsor EDC); real-time eligibility check (EHR pull); IRB sign-off gate; dedicated third-model bias auditor (parole bias-gate parallel).

- [ ] **Step 1-9:** Follow Task 6 sequence: 9 tests (8 base + 1 extra for bias-veto specifically), full implementation, 4 templates, example (synthetic cardiology RCT scenario: 68yo Black woman with HFrEF — eligibility check that surfaces both clinical inclusion AND under-representation considerations), run suite (542 passed), commit:

```bash
git add src/adv_multi_agent/healthcare/workflows/clinical_trial_eligibility.py \
        src/adv_multi_agent/healthcare/skills/templates/trial_*.md \
        tests/unit/test_clinical_trial_eligibility.py \
        examples/healthcare/clinical_trial_eligibility.py
git commit -m "feat(healthcare): ClinicalTrialEligibilityWorkflow (veto on safety exclusion or protected-class bias)"
```

---

## Task 10: Update decisions.md and scenarios.md

**Files:**
- Modify: `docs/decisions.md`
- Modify: `docs/scenarios.md`

- [ ] **Step 1: Append D-HEALTH-1..4 rows to decisions.md**

Find the last `D-IND-*` row. After it, append:
```markdown
| D-HEALTH-1 | 2026-05-16 | MVP-8 of 27-workflow healthcare catalog (DiagnosisCodeAudit, DischargePlanningRisk, PriorAuthorizationReview, ClaimsAppealReview, DrugInteractionFlagging [veto], AdverseEventTriage [veto], TreatmentPlanReview [veto], ClinicalTrialEligibility [veto]). 19 Phase-2 designs locked in design doc. Same no-domain-base-class rule as D-IND-1. | docs/superpowers/specs/2026-05-16-healthcare-domain-design.md |
| D-HEALTH-2 | 2026-05-16 | Score threshold 8.0 for all 4 veto-using healthcare workflows (vs 7.5 elsewhere). Justified by patient-safety + regulatory stakes (FDA 7/15-day, ICH E2A, IRB irreversibility). | docs/superpowers/specs/2026-05-16-healthcare-domain-design.md |
| D-HEALTH-3 | 2026-05-16 | All patient-identifying fields are caller-supplied free-text; PHI de-identification is caller's responsibility; every workflow docstring lists this as PRODUCTION_GAP #1. The workflow applies sanitize_for_prompt but cannot validate upstream de-identification. | docs/superpowers/specs/2026-05-16-healthcare-domain-design.md |
| D-HEALTH-4 | 2026-05-16 | Veto trigger language in reviewer criteria templates references specific regulatory citations (FDA 21 CFR 312 7/15-day expedited report, ICH E2A serious/unexpected definitions, IRB exclusion criteria) — not generic "safety concern" phrasing. Ensures the directive is precise enough for the human-in-the-loop to act on. | docs/superpowers/specs/2026-05-16-healthcare-domain-design.md |
```

- [ ] **Step 2: Update scenarios.md healthcare section**

Find the "Other Domains (future)" table. Remove the two healthcare rows. Add a new section above:

```markdown
## Healthcare (`src/adv_multi_agent/healthcare/`)
> Clinical decision support + payer operations + drug safety

| Scenario | Status | Notes |
|---|---|---|
| Diagnosis code audit | **built** | DiagnosisCodeAuditWorkflow — ACCURACY + COMPLIANCE + SPECIFICITY flags |
| Discharge planning risk | **built** | DischargePlanningRiskWorkflow — READMISSION + CARE-GAP + SOCIAL-DETERMINANT flags |
| Prior authorization review | **built** | PriorAuthorizationReviewWorkflow — MEDICAL-NECESSITY + COVERAGE + DOCUMENTATION flags |
| Claims appeal review | **built** | ClaimsAppealReviewWorkflow — EVIDENCE + COVERAGE + PROCEDURE flags |
| Drug interaction flagging | **built** | DrugInteractionFlaggingWorkflow — SEVERITY + EVIDENCE + CONTRAINDICATION flags; reviewer-veto on absolute contraindication / QTc / NTI / cross-allergy |
| Adverse event triage | **built** | AdverseEventTriageWorkflow — SEVERITY + CAUSALITY + REGULATORY flags; reviewer-veto on serious-unexpected ADR triggering FDA 7/15-day expedited report |
| Treatment plan review | **built** | TreatmentPlanReviewWorkflow — GUIDELINE + CONTRAINDICATION + RISK flags; reviewer-veto on absolute contraindication |
| Clinical trial eligibility | **built** | ClinicalTrialEligibilityWorkflow — BIAS + ELIGIBILITY + EVIDENCE flags; reviewer-veto on safety exclusion or protected-class bias; bias-gate pattern from parole applied clinically |
```

Update the "Last updated" date to `2026-05-16`.

- [ ] **Step 3: Commit**

```bash
git add docs/decisions.md docs/scenarios.md
git commit -m "docs: log D-HEALTH-1..4 + mark 8 healthcare workflows built in scenarios"
```

---

## Task 11: Refresh README.md and CLAUDE.md for 6-domain state

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update README.md headline counts**

Find the line citing current totals (e.g. "23 workflows · 481 tests · 107 skill templates"). Change to:
- **31 workflows** (23 + 8 healthcare)
- **~545 tests** (481 + ~64 healthcare = 8 tests × 4 non-veto + 9 tests × 4 veto = ~68; verify exact count from final pytest run)
- **139 skill templates** (107 + 32)
- **6 domains** (research, parole, retail, pc, industrial, healthcare)

Update the package tree section to show the `healthcare/` package alongside the others.

Add to the per-domain MCP registration block:
```bash
SKILLS_DOMAIN=healthcare claude mcp add adv-multi-agent-healthcare -- python -m adv_multi_agent.core.skills.mcp_server
```

Update bundled-template count in the Architecture notes ("139 bundled templates (15 research + 6 parole + 25 retail + 29 pc + 32 industrial + 32 healthcare)").

- [ ] **Step 2: Update CLAUDE.md**

Find the "Currently-shipped domains" line. Update to: `research, parole, retail, pc, industrial, healthcare`.

Update the workflow/test/skills count line to match the new totals.

Update the "Reference docs" subsection if it lists per-domain design docs to add the healthcare design.

- [ ] **Step 3: Commit**

```bash
git add README.md CLAUDE.md
git commit -m "docs: refresh README and CLAUDE.md for 6-domain state (31 workflows, ~545 tests, 139 skills)"
```

---

## Task 12: Security audit on the healthcare surface

**Files:**
- Create: `docs/security-audits/2026-05-16-healthcare-sweep.md`

- [ ] **Step 1: Spawn the security-audit subagent**

Use the Agent tool with `subagent_type: "general-purpose"`. Brief it per the `security-audit` skill template, scoped to the healthcare surface:

Files to read (provide the complete list):
- All 8 files under `src/adv_multi_agent/healthcare/workflows/`
- `src/adv_multi_agent/healthcare/__init__.py`
- `src/adv_multi_agent/core/skills/registry.py` (allowlist change)
- All 32 files under `src/adv_multi_agent/healthcare/skills/templates/`
- All 8 files under `tests/unit/test_*` for healthcare workflows
- All 8 files under `examples/healthcare/`
- `docs/superpowers/specs/2026-05-16-healthcare-domain-design.md` (for design context)

Stack hint: "python multi-agent library; healthcare domain; PHI in free-text inputs; reviewer-veto + triple-flag convergence patterns; shared parsers in core/_internal.py"

Attack surfaces specific to healthcare to enumerate (add to the generic security-audit prompt):
1. **PHI in free-text Request fields** — workflow applies `sanitize_for_prompt` but cannot validate de-identification; how does the workflow surface (or fail to surface) when PHI is detected in inputs?
2. **Reviewer veto on patient-safety conditions** — verify the audit-trail-before-veto-break invariant holds for all 4 veto workflows (wiki.add_feedback BEFORE the veto check)
3. **`first_draft` preservation in metadata** — verify L-IND-2 closure: every vetoed run has `metadata['first_draft']` containing the clean executor draft
4. **Score threshold 8.0** — verify it is encoded in the workflow's score check, not just in the criteria template; an executor that just hits 7.5 must not converge
5. **Flag header parser** — verify `SOCIAL-DETERMINANT FLAGS` and `MEDICAL-NECESSITY FLAGS` hyphenated headers extract correctly (H-IND-1 hyphen-tolerant sibling-stop)
6. **Bias-gate template language** — D-HEALTH-4 — verify the trial-eligibility criteria template names protected-class attributes explicitly and does NOT inadvertently exclude clinically-justified demographic eligibility (e.g. pediatric trial)
7. **Test-shape pitfall** — verify all flag-extractor tests use `assert flags == [...]` or `assert len(flags) == N`, NOT `any(...)` (recurring failure mode H-IND-1)

Output report to `docs/security-audits/2026-05-16-healthcare-sweep.md` (let the subagent write it directly).

- [ ] **Step 2: Triage findings**

Read the audit report. For each finding:
- **CRITICAL / HIGH:** fix inline before final commit
- **MEDIUM:** fix inline if scope-fit; else log as backlog (`L-HEALTH-*` row in the audit report)
- **LOW:** log as backlog; close in a follow-up if cheap

Tracker pattern from prior audits: each finding gets a code `H-HEALTH-1` / `M-HEALTH-1` / `L-HEALTH-1` and a status row at the bottom of the audit report.

- [ ] **Step 3: Apply CRITICAL/HIGH fixes**

For each high-severity finding, write the fix as a self-contained edit + regression test. Re-run the test suite after each fix. Commit each fix separately so the audit trail is clear.

- [ ] **Step 4: Final full test suite + lint**

```bash
python -m pytest tests/ -q
python -m mypy src/ --strict
python -m ruff check src/
```
Expected: all tests pass; mypy + ruff clean.

- [ ] **Step 5: Commit audit report + any remediations**

```bash
git add docs/security-audits/2026-05-16-healthcare-sweep.md
# Plus any remediation files from Step 3
git commit -m "audit(healthcare): security sweep — N CRIT / N HIGH / N MED / N LOW; CRIT+HIGH closed pre-commit"
```

---

## Task 13: Integration smoke test + final docs refresh

**Files:**
- Modify: `docs/NEXT_SESSION.md`
- Modify: `~/.claude/projects/.../memory/project_state.md`

- [ ] **Step 1: Run final full test suite**

```bash
python -m pytest tests/ -q --tb=short
python -m mypy src/ tests/ --strict
python -m ruff check src/ tests/
```

Confirm:
- Test count = 481 (prior) + 64 (healthcare: ~7 non-veto × 4 + ~9 veto × 4) = ~545
- All tests pass
- mypy + ruff clean

- [ ] **Step 2: Smoke-test the package import**

```bash
python -c "from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import ClinicalTrialEligibilityWorkflow; print(ClinicalTrialEligibilityWorkflow.__doc__[:200])"
python -c "from adv_multi_agent.core.skills.registry import SkillRegistry; print(SkillRegistry.bundled_skills_path('healthcare'))"
```
Expected: workflow docstring prints; healthcare templates path resolves.

- [ ] **Step 3: Test the MCP server domain dispatch**

```bash
SKILLS_DOMAIN=healthcare python -m adv_multi_agent.core.skills.mcp_server --help 2>&1 | head -5
```
Expected: server starts (or prints --help cleanly without erroring on the healthcare domain).

- [ ] **Step 4: Update NEXT_SESSION.md**

Add a new section at the top under "Current state":
```markdown
### 2026-05-16 — Healthcare domain SHIPPED — MVP-8 + audit closed

**Commits:** see git log between `0a12c72` (design doc) and HEAD. Direct to main per repo convention.

- 8 MVP workflows (4 non-veto + 4 veto) + 32 skill templates + 8 examples + 8 unit-test files
- D-HEALTH-1..4 decision rows
- Security audit 2026-05-16: see `docs/security-audits/2026-05-16-healthcare-sweep.md`
- 19 Phase-2 designs locked in `docs/superpowers/specs/2026-05-16-healthcare-domain-design.md`
```

Update the headline counts at the top of NEXT_SESSION.md.

- [ ] **Step 5: Update project_state.md**

Bump:
- 5 domains → **6 domains**
- 23 workflows → **31 workflows**
- 7 veto-using → **11 veto-using** (7 + 4 healthcare)
- 481 tests → **~545 tests**
- 107 skill templates → **139 skill templates**

Add `healthcare` to the domain list with workflow names. Append a row to the audit history table for 2026-05-16.

- [ ] **Step 6: Final commit + push**

```bash
git add docs/NEXT_SESSION.md
# project_state.md is in the global memory dir, separate commit/save
git commit -m "docs: refresh NEXT_SESSION for healthcare MVP ship"
git push
```

Save `project_state.md` via the memory mechanism (Write tool to the absolute path).

---

## Self-review

**1. Spec coverage:** Every section of the design doc maps to a task —
- Domain decisions D-HEALTH-1..4 → Task 10
- Convention recap (10 rules from retail lineage) → embedded in each workflow's Step 3
- Package structure → Task 1
- 8 MVP workflow specs (sections 1–8 of design doc) → Tasks 2–9
- Phase-2 catalog → not built (intentional; locked in design doc only; no plan task needed)
- Universal PRODUCTION_GAPS → embedded in each workflow's module docstring
- Build sequence (DiagnosisCodeAudit → ... → ClinicalTrialEligibility) → Tasks 2–9 ordering matches design doc § "Build sequence (MVP-8)"

**2. Placeholder scan:** No `TBD`, `TODO`, `fill in details`. The phrases "Follow Task 2's full code as the structural template" / "Follow Task 6 sequence" are pattern references to **specific file paths within this plan**, not forward references — they tell the engineer to read Task 2 / Task 6 directly. Where workflow-class code differs, every substitution is enumerated (field list, flag headers, banner dict entries, metadata keys, checklist items). The reference-implementation files (`industrial/workflows/supplier_qualification.py`, `industrial/workflows/product_liability_root_cause.py`) are listed in the header.

**3. Type consistency:**
- Request dataclass name pattern: `<Workflow>Request` (e.g. `DiagnosisCodeAuditRequest`) — consistent across all 8
- Workflow class name pattern: `<Name>Workflow` — consistent
- `_MAX_FIELD_CHARS = 1500` — same value across all 8
- Score thresholds: 7.5 for 4 non-veto / 8.0 for 4 veto — matches design spec D-HEALTH-2
- Flag header dict pattern: `_FLAG_HEADERS: tuple[str, ...] = (...)` — consistent
- Metadata snake_case key pattern: lowercase flag-name + `_flags` — consistent
- Checklist owner prefix `[OWNER: <role>]` — consistent across all 8
- Test class names: `TestRequestToPromptText`, `TestConvergence`, `TestVeto` (veto only), `TestMetadata`, `TestDisclaimer` — consistent
- Skill template input keys match Request field names — consistent

**4. Spec-requirement → task gaps:** None identified.

---

## Execution Handoff

**Plan complete and saved to `docs/superpowers/plans/2026-05-16-healthcare-domain.md`.**

Two execution options:

1. **Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration. Best for an 8-workflow plan where each task is independently testable.

2. **Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints. Best if you want to watch each task land.

Which approach?
