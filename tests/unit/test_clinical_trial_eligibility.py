"""Unit tests for ClinicalTrialEligibilityWorkflow — no live API calls.

Veto + triple-flag bias-gate (D-HEALTH-4). Mirrors test_treatment_plan_review.py shape:
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when bias flags present (1-round limit)
- safety veto halts loop with first_draft preserved (L-IND-2)
- bias veto halts loop (protected-class attribute determinative without justification)
- no veto when directive is None
- all metadata keys present on clean run
- disclaimer in output on clean run
- checklist owner is IRB Coordinator / Principal Investigator
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
    ClinicalTrialEligibilityWorkflow,
    TrialEligibilityRequest,
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


def make_request(**kwargs: Any) -> TrialEligibilityRequest:
    """68yo Black woman with HFrEF — cardiology RCT eligibility check.
    Exercises both clinical inclusion criteria and under-representation
    considerations (JAMA 2019 cardiology RCT bias pattern).
    """
    defaults: dict[str, Any] = dict(
        trial_id="NCT-CARDIO-2026-001",
        protocol_summary=(
            "Phase III RCT of novel SGLT2 inhibitor for HFrEF. "
            "Inclusion §3.1: NYHA Class II-IV, LVEF < 40%, age 18-80. "
            "Exclusion §4.1: eGFR < 20 mL/min, active infection, "
            "prohibited concomitant SGLT2 inhibitor. "
            "§4.2: No sex/race/ethnicity exclusions; all demographics eligible."
        ),
        patient_profile=(
            "68-year-old Black woman, NYHA Class III HFrEF (LVEF 32%), "
            "type 2 diabetes (HbA1c 7.8%), eGFR 48 mL/min/1.73m². "
            "No active infection. Non-smoker. BMI 29."
        ),
        biomarker_status=(
            "LVEF: 32% (echo, 2026-05-01). BNP: 720 pg/mL. "
            "eGFR: 48 mL/min/1.73m² (CKD2). HbA1c: 7.8%. "
            "No troponin elevation. Na: 137 mEq/L. K: 4.3 mEq/L."
        ),
        prior_treatments=(
            "Sacubitril/valsartan 97/103mg BID (on board 12 months). "
            "Metoprolol succinate 50mg daily. Furosemide 40mg daily. "
            "No prior SGLT2 inhibitor. No washout required."
        ),
        competing_risks=(
            "CKD Stage 2 (eGFR 48) — above §4.1 exclusion threshold of eGFR < 20. "
            "Type 2 diabetes — SGLT2 inhibitor glycaemic benefit is protocol-noted "
            "secondary endpoint. No active infection documented."
        ),
        site_context=(
            "Enrolling site: Academic medical centre, urban population. "
            "Current cohort: 78% male, 82% non-Hispanic white. "
            "Under-representation of Black women noted in site enrollment log "
            "relative to HFrEF disease prevalence in catchment area."
        ),
    )
    defaults.update(kwargs)
    return TrialEligibilityRequest(**defaults)


def clean_critique() -> str:
    return (
        "Eligibility assessment thorough; protocol citations present; "
        "biomarker evidence grounded in input data; no bias signal detected.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm eGFR value from primary lab, not free-text summary\n"
        "BIAS FLAGS: None detected\n"
        "ELIGIBILITY FLAGS: None detected\n"
        "EVIDENCE FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Protocol fidelity check
§3.1 Inclusion: NYHA Class III confirmed (patient_profile); LVEF 32% < 40%
threshold (biomarker_status); age 68 within 18-80 range (patient_profile).
§4.1 Exclusion: eGFR 48 is above the < 20 mL/min exclusion threshold
(biomarker_status); no active infection (patient_profile); no prior SGLT2
inhibitor use (prior_treatments) — no washout required.
§4.2: No sex/race/ethnicity exclusions apply.

## Bias detection
Patient is a 68-year-old Black woman. Protocol §4.2 explicitly states no
sex/race/ethnicity exclusions. No protected-class attribute functions as a
determinative exclusion factor. Site enrollment log notes under-representation
of Black women relative to HFrEF disease prevalence — this is a site enrollment
issue, not a protocol exclusion. No JAMA 2019-pattern bias signal in the
eligibility reasoning.

## Evidence grounding
LVEF 32%: cited from biomarker_status (echo, 2026-05-01).
eGFR 48: cited from biomarker_status (CKD2).
No prior SGLT2 inhibitor: cited from prior_treatments.
No active infection: cited from patient_profile.

## Safety exclusion verification
eGFR exclusion (§4.1 threshold < 20): patient eGFR 48 — above threshold;
not excluded. No organ dysfunction exclusion applies.
Prohibited concomitant medication exclusion (§4.1 SGLT2 inhibitor): none
documented in prior_treatments — not excluded.
Active infection exclusion (§4.1): none documented in patient_profile — not excluded.

## Eligibility determination
ELIGIBLE per protocol §3.1 and §4.1. All inclusion criteria met; no exclusion
criteria triggered. Site coordinator should document eligibility rationale in
regulatory binder per ICH-GCP.

## Claims
[Source: biomarker_status] LVEF 32% — meets §3.1 LVEF < 40% inclusion criterion.
[Source: biomarker_status] eGFR 48 mL/min — above §4.1 exclusion threshold of < 20.
[Source: prior_treatments] No prior SGLT2 inhibitor — no washout required.
"""

_SAFETY_VETO_CRITIQUE = (
    "Assessment identifies eGFR 48 but fails to cross-reference with prohibited "
    "concomitant medication check per §4.1.\n\n"
    "Overall score: 8.1/10\n"
    "Key issues:\n"
    "- Patient is on sacubitril/valsartan — draft does not verify this is not a "
    "prohibited concomitant medication per the protocol\n"
    "BIAS FLAGS: None detected\n"
    "ELIGIBILITY FLAGS:\n"
    "- Draft marks patient eligible without explicitly verifying sacubitril/valsartan "
    "against §4.1 prohibited concomitant medication list; if protocol prohibits ARNi "
    "combination, patient meets safety exclusion\n"
    "EVIDENCE FLAGS: None detected\n"
    "REVIEWER VETO: Patient meets potential safety exclusion criterion — sacubitril/"
    "valsartan is listed as a prohibited concomitant medication in §4.1 of the protocol "
    "but the assessment marks the patient eligible without explicitly verifying this. "
    "Per ICH-GCP, enrolling a patient meeting a safety exclusion is a serious protocol "
    "deviation. Escalate to PI before any enrollment action."
)

_BIAS_VETO_CRITIQUE = (
    "Assessment uses patient race and sex as determinative factors without "
    "protocol-specified clinical justification.\n\n"
    "Overall score: 7.8/10\n"
    "Key issues:\n"
    "- Race and sex appear as determinative exclusion factors without §4.2 override\n"
    "BIAS FLAGS:\n"
    "- Draft reasoning cites patient's Black race and female sex as factors "
    "limiting eligibility without protocol-specified clinical justification; "
    "§4.2 explicitly permits all demographics; this pattern mirrors JAMA 2019 "
    "cardiology RCT under-representation documented by Duma et al.\n"
    "ELIGIBILITY FLAGS: None detected\n"
    "EVIDENCE FLAGS: None detected\n"
    "REVIEWER VETO: Protected-class bias signal — draft uses Black race and female "
    "sex as determinative eligibility factors without protocol-specified clinical "
    "justification. Protocol §4.2 explicitly states no sex/race/ethnicity exclusions. "
    "This pattern is consistent with demographic under-representation documented in "
    "JAMA 2019 cardiology RCT literature (Duma et al., JAMA Cardiol. 2019;4(3):211-219). "
    "Escalate to IRB coordinator; do not enroll or exclude on this basis."
)


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Trial ID:",
            "Protocol summary:",
            "Patient profile:",
            "Biomarker status:",
            "Prior treatments:",
            "Competing risks:",
            "Site context:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(protocol_summary=oversized).to_prompt_text()
        protocol_section = text.split("Protocol summary:")[1].split("\n")[0]
        assert len(protocol_section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalTrialEligibilityWorkflow(
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

    async def test_does_not_converge_when_bias_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: protected-class attribute used without protocol justification\n"
            "BIAS FLAGS:\n"
            "- Race cited as eligibility factor without protocol-specified clinical basis\n"
            "ELIGIBILITY FLAGS: None detected\n"
            "EVIDENCE FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = ClinicalTrialEligibilityWorkflow(
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
        assert len(result.metadata["bias_flags"]) == 1
        assert "Race" in result.metadata["bias_flags"][0]


@pytest.mark.asyncio
class TestVeto:
    async def test_safety_veto_halts_loop(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalTrialEligibilityWorkflow(
            executor=FakeExecutor(["initial draft", "draft2", "draft3"]),
            reviewer=FakeReviewer(
                [make_review(8.1, approved=True, critique=_SAFETY_VETO_CRITIQUE)]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert "veto_reason" in result.metadata
        assert "safety exclusion" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_bias_veto_halts_loop(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalTrialEligibilityWorkflow(
            executor=FakeExecutor(["bias draft", "draft2"]),
            reviewer=FakeReviewer(
                [make_review(7.8, approved=True, critique=_BIAS_VETO_CRITIQUE)]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert "veto_reason" in result.metadata
        assert "bias signal" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "bias draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalTrialEligibilityWorkflow(
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
        wf = ClinicalTrialEligibilityWorkflow(
            executor=FakeExecutor(["draft"]),
            reviewer=FakeReviewer(
                [make_review(8.1, approved=True, critique=_SAFETY_VETO_CRITIQUE)]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        checklist = result.metadata["trial_checklist"]
        veto_items = [item for item in checklist if "VETO" in item]
        assert len(veto_items) == 1


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_all_required_keys(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalTrialEligibilityWorkflow(
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
            "trial_id",
            "bias_flags",
            "eligibility_flags",
            "evidence_flags",
            "trial_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata

    async def test_trial_id_in_metadata(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalTrialEligibilityWorkflow(
            executor=FakeExecutor([_GOOD_OUTPUT]),
            reviewer=FakeReviewer(
                [make_review(8.5, approved=True, critique=clean_critique())]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["trial_id"] == "NCT-CARDIO-2026-001"

    async def test_checklist_owner_is_irb_pi(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalTrialEligibilityWorkflow(
            executor=FakeExecutor([_GOOD_OUTPUT]),
            reviewer=FakeReviewer(
                [make_review(8.5, approved=True, critique=clean_critique())]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["trial_checklist"][0] == (
            "[OWNER: IRB Coordinator / Principal Investigator]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output_on_clean_run(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalTrialEligibilityWorkflow(
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
        wf = ClinicalTrialEligibilityWorkflow(
            executor=FakeExecutor(["draft"]),
            reviewer=FakeReviewer(
                [make_review(8.1, approved=True, critique=_SAFETY_VETO_CRITIQUE)]
            ),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
