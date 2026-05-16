"""Unit tests for TreatmentPlanReviewWorkflow — no live API calls.

Veto + triple-flag (D-HEALTH-4). Mirrors test_adverse_event_triage.py shape:
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when guideline flags present (1-round limit)
- veto halts loop with first_draft preserved (L-IND-2)
- no veto when directive is None
- all metadata keys present on clean run
- disclaimer in output on clean run
- checklist owner line is attending physician
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.healthcare.workflows.treatment_plan_review import (
    TreatmentPlanRequest,
    TreatmentPlanReviewWorkflow,
    _DISCLAIMER,
    _MAX_FIELD_CHARS,
    _VETO_BANNER,
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


def make_review(score: float, *, approved: bool, critique: str = "") -> ReviewResult:
    return ReviewResult(score=score, critique=critique, suggestions=[], approved=approved)


def make_request(**kwargs: Any) -> TreatmentPlanRequest:
    """70yo CHF + CKD3 patient — contrast-enhanced procedure triggers veto."""
    defaults: dict[str, Any] = dict(
        patient_summary=(
            "70-year-old male with NYHA Class III CHF (EF 35%), CKD Stage 3a "
            "(eGFR 42 mL/min/1.73m²), type 2 diabetes, hypertension. "
            "No documented drug allergies."
        ),
        proposed_plan=(
            "1. Coronary angiography with iodinated contrast (60 mL) to evaluate "
            "suspected coronary artery disease. "
            "2. Continue furosemide 40mg daily for volume management. "
            "3. Add lisinopril 5mg daily for RAAS blockade."
        ),
        current_medications=(
            "Furosemide 40mg daily, metformin 1000mg BID, amlodipine 5mg daily, "
            "aspirin 81mg daily."
        ),
        lab_values=(
            "eGFR: 42 mL/min/1.73m² (CKD3a). Creatinine: 1.6 mg/dL. "
            "BNP: 820 pg/mL. Na: 138 mEq/L. K: 4.1 mEq/L. "
            "LFTs within normal limits."
        ),
        clinical_guidelines=(
            "ACC/AHA 2022 Heart Failure Guideline; KDIGO 2012 CKD Guideline; "
            "ACR Manual on Contrast Media 2023."
        ),
        contraindication_context=(
            "CKD3a (eGFR 42) — iodinated contrast carries contrast-induced "
            "nephropathy (CIN) risk; ACR threshold for prophylaxis is eGFR < 45. "
            "Metformin must be held 48h post-contrast per ACR guidelines. "
            "No documented allergies to contrast agents."
        ),
    )
    defaults.update(kwargs)
    return TreatmentPlanRequest(**defaults)


def clean_critique() -> str:
    return (
        "Treatment plan review thorough; guideline citations present; "
        "contraindications checked against lab values.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm prophylaxis protocol documented\n"
        "GUIDELINE FLAGS: None detected\n"
        "CONTRAINDICATION FLAGS: None detected\n"
        "RISK FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Guideline review
ACC/AHA 2022 HF Guideline §7.3: RAAS inhibition with ACE inhibitor indicated
for HFrEF (EF < 40%); lisinopril 5mg daily is guideline-concordant initial dose.
KDIGO 2012 CKD §3.1.1: eGFR 42 classifies as CKD Stage 3a; dose adjustment
required for renally-cleared agents.
ACR Manual on Contrast Media 2023 §4: eGFR 30–44 — contrast use requires
pre-hydration prophylaxis (IV NS 1 mL/kg/h for 3–4h pre-procedure and 6h
post-procedure); N-acetylcysteine 600mg BID the day before and day of procedure.

## Contraindication check
Drug-organ (contrast-CKD): Iodinated contrast in eGFR 42 — CIN risk present;
prophylaxis required per ACR 2023 §4; mechanism: contrast-mediated renal
vasoconstriction and direct tubular toxicity in impaired kidneys.
Drug-organ (metformin-contrast): Metformin must be held at time of contrast
administration and for 48h post-procedure (lactic acidosis risk in AKI);
mechanism: metformin clearance dependent on renal function; contrast-induced
AKI could precipitate metformin accumulation.
No drug-allergy contraindications documented.

## Risk stratification
CIN risk (Mehran score): age 70 + eGFR 42 + CHF (EF 35%) + contrast volume
60 mL → estimated CIN risk 7-15%; prophylaxis reduces risk by ~50%.
RAAS: lisinopril addition in CKD3 — monitor K and creatinine at 1-2 weeks;
eGFR 42 does not preclude ACE inhibitor per KDIGO 2022 CKD-MBD §2.

## Plan revisions
Coronary angiography: Add pre-hydration IV NS 1 mL/kg/h × 4h pre-procedure
and 6h post-procedure. Add N-acetylcysteine 600mg BID day before and day of.
Hold metformin at time of contrast; resume 48h post if creatinine stable.
Furosemide 40mg daily: No change required.
Lisinopril 5mg daily: No change required. Check K and Cr at 1 week post-start.

## Claims
[Source: lab_values] eGFR 42 mL/min/1.73m² — CKD Stage 3a per KDIGO 2012.
[Source: contraindication_context] eGFR < 45 triggers ACR 2023 CIN prophylaxis protocol.
[Source: current_medications] Metformin 1000mg BID — must be held at contrast administration.
"""

_VETO_CRITIQUE = (
    "Treatment plan identifies contrast use in CKD3 but does not include prophylaxis "
    "in the proposed plan — CIN risk unmitigated.\n\n"
    "Overall score: 8.2/10\n"
    "Key issues:\n- Contrast-enhanced procedure in CKD3a without documented prophylaxis\n"
    "GUIDELINE FLAGS: None detected\n"
    "CONTRAINDICATION FLAGS:\n"
    "- Contrast-enhanced procedure (60 mL iodinated) in CKD3a (eGFR 42) without "
    "IV hydration prophylaxis; ACR 2023 §4 requires prophylaxis for eGFR < 45\n"
    "RISK FLAGS: None detected\n"
    "REVIEWER VETO: Procedure contraindicated without prophylaxis — "
    "iodinated contrast (60 mL) in CKD3a patient (eGFR 42, threshold < 45 per ACR 2023 §4) "
    "without pre-hydration or N-acetylcysteine prophylaxis documented in the proposed plan. "
    "Escalate to attending physician; do not schedule contrast procedure until prophylaxis "
    "protocol is confirmed in the order set."
)


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Patient summary:",
            "Proposed plan:",
            "Current medications:",
            "Lab values:",
            "Clinical guidelines:",
            "Contraindication context:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(proposed_plan=oversized).to_prompt_text()
        plan_section = text.split("Proposed plan:")[1].split("\n")[0]
        assert len(plan_section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = TreatmentPlanReviewWorkflow(
            executor=FakeExecutor([_GOOD_OUTPUT]),
            reviewer=FakeReviewer(
                [make_review(8.5, approved=True, critique=clean_critique())]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_guideline_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: guideline citations missing for contrast prophylaxis\n"
            "GUIDELINE FLAGS:\n"
            "- Contrast prophylaxis recommended without citing ACR 2023 §4\n"
            "CONTRAINDICATION FLAGS: None detected\n"
            "RISK FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = TreatmentPlanReviewWorkflow(
            executor=FakeExecutor([_GOOD_OUTPUT]),
            reviewer=FakeReviewer(
                [make_review(7.5, approved=True, critique=critique)]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert len(result.metadata["guideline_flags"]) == 1
        assert "ACR" in result.metadata["guideline_flags"][0]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = TreatmentPlanReviewWorkflow(
            executor=FakeExecutor(["initial draft", "draft2", "draft3"]),
            reviewer=FakeReviewer(
                [make_review(8.2, approved=True, critique=_VETO_CRITIQUE)]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert "veto_reason" in result.metadata
        assert "contraindicated" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = TreatmentPlanReviewWorkflow(
            executor=FakeExecutor(["draft"]),
            reviewer=FakeReviewer(
                [make_review(8.5, approved=True, critique=clean_critique())]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert "veto_reason" not in result.metadata
        assert "vetoed" not in result.metadata

    async def test_veto_checklist_has_stop_item(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = TreatmentPlanReviewWorkflow(
            executor=FakeExecutor(["draft"]),
            reviewer=FakeReviewer(
                [make_review(8.2, approved=True, critique=_VETO_CRITIQUE)]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        checklist = result.metadata["treatment_checklist"]
        veto_items = [item for item in checklist if "VETO" in item]
        assert len(veto_items) == 1


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_all_required_keys(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = TreatmentPlanReviewWorkflow(
            executor=FakeExecutor([_GOOD_OUTPUT]),
            reviewer=FakeReviewer(
                [make_review(8.5, approved=True, critique=clean_critique())]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "patient_summary_chars",
            "guideline_flags",
            "contraindication_flags",
            "risk_flags",
            "treatment_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata

    async def test_checklist_owner_is_attending_physician(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = TreatmentPlanReviewWorkflow(
            executor=FakeExecutor([_GOOD_OUTPUT]),
            reviewer=FakeReviewer(
                [make_review(8.5, approved=True, critique=clean_critique())]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["treatment_checklist"][0] == "[OWNER: Attending Physician]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output_on_clean_run(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = TreatmentPlanReviewWorkflow(
            executor=FakeExecutor([_GOOD_OUTPUT]),
            reviewer=FakeReviewer(
                [make_review(8.5, approved=True, critique=clean_critique())]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output

    async def test_disclaimer_in_output_on_veto(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = TreatmentPlanReviewWorkflow(
            executor=FakeExecutor(["draft"]),
            reviewer=FakeReviewer(
                [make_review(8.2, approved=True, critique=_VETO_CRITIQUE)]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    """L-HEALTH-3: zero flags + no veto but approved=False (score below threshold) must not converge."""

    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        clean_critique = (
            "GUIDELINE FLAGS: None detected\n"
            "CONTRAINDICATION FLAGS: None detected\n"
            "RISK FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=clean_critique),
            make_review(7.9, approved=False, critique=clean_critique),
            make_review(7.9, approved=False, critique=clean_critique),
        ])
        wf = TreatmentPlanReviewWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
