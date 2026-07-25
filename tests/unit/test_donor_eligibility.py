"""Unit tests for DonorEligibilityWorkflow (Lifesciences CGT · veto) — no live API.

Veto + triple-flag (D-LIFESCI-8) + L-HEALTH-1 first_draft preservation.
Mirrors the se510k veto shape.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.donor_eligibility import (
    DonorEligibilityWorkflow,
    DonorEligibilityRequest,
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


def make_request(**kwargs: Any) -> DonorEligibilityRequest:
    defaults: dict[str, Any] = dict(
        donation_type="Allogeneic living donor.",
        donor_screening_summary=(
            "Risk-factor history questionnaire completed; no relevant risk factors "
            "identified; physical assessment unremarkable."
        ),
        donor_testing_summary=(
            "Testing for the relevant communicable-disease agents was performed by "
            "the required methods; all results non-reactive."
        ),
        agents_considered=(
            "The relevant communicable-disease agents required for a living donor "
            "were considered."
        ),
        plasma_dilution_assessment=(
            "Plasma dilution assessed and within the acceptable algorithm limit."
        ),
        physical_assessment_or_records_review=(
            "Physical assessment and available records reviewed; no findings of "
            "concern."
        ),
        retesting_or_repeat_status="Not a repeat donor; no retesting required.",
        urgent_medical_need_flag="No urgent-medical-need path invoked.",
    )
    defaults.update(kwargs)
    return DonorEligibilityRequest(**defaults)


def clean_critique() -> str:
    return (
        "Screening complete; testing adequate; eligible call supported.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm testing dates precede recovery\n"
        "SCREENING-GAP FLAGS: None detected\n"
        "TESTING-GAP FLAGS: None detected\n"
        "INELIGIBLE-RELEASE FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Donor screening
Risk-factor history complete; physical assessment unremarkable.

## Communicable-disease testing
Required agents tested by the right methods; non-reactive.

## Eligibility determination
The eligible call is consistent with screening and testing.

## Plasma dilution and urgent-need documentation
Plasma dilution within limit; no urgent-need path invoked.

## Eligibility conclusion
The donor is eligible on the supplied evidence.

## Claims
[Source: donor_testing_summary] Required agents non-reactive.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Donation type:",
            "Donor screening summary:",
            "Donor testing summary:",
            "Agents considered:",
            "Plasma-dilution assessment:",
            "Physical assessment / records review:",
            "Retesting / repeat status:",
            "Urgent-medical-need flag:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(donor_screening_summary=oversized).to_prompt_text()
        section = text.split("Donor screening summary:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = DonorEligibilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_screening_gap_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: incomplete screening\n"
            "SCREENING-GAP FLAGS:\n"
            "- The risk-factor history omits the required travel-exposure question\n"
            "TESTING-GAP FLAGS: None detected\n"
            "INELIGIBLE-RELEASE FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = DonorEligibilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["screening_gap_flags"] == [
            "The risk-factor history omits the required travel-exposure question"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: incomplete screening\n"
            "SCREENING-GAP FLAGS:\n"
            "- The risk-factor history omits the required travel-exposure question\n"
            "RECOMMENDATION: re-administer the screening questionnaire\n"
            "TESTING-GAP FLAGS: None detected\n"
            "INELIGIBLE-RELEASE FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = DonorEligibilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["screening_gap_flags"] == [
            "The risk-factor history omits the required travel-exposure question"
        ]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop_and_preserves_first_draft(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: reactive test result\n"
            "SCREENING-GAP FLAGS: None detected\n"
            "TESTING-GAP FLAGS: None detected\n"
            "INELIGIBLE-RELEASE FLAGS: None detected\n"
            "REVIEWER VETO: A required communicable-disease test is reactive and no "
            "eligibility exception applies; the donor is ineligible. Releasing the "
            "allogeneic product would risk communicable-disease transmission. Do not "
            "release."
        )
        config = make_config(tmp_path)
        wf = DonorEligibilityWorkflow(
            executor=FakeExecutor(responses=["initial draft", "draft2", "draft3"]),
            reviewer=FakeReviewer(results=[make_review(9.0, approved=True, critique=veto_critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert "veto_reason" in result.metadata
        assert "ineligible" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        # L-HEALTH-1: first_draft preserved for the QA / Tissue-safety officer.
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = DonorEligibilityWorkflow(
            executor=FakeExecutor(responses=["draft"]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert "veto_reason" not in result.metadata
        assert "vetoed" not in result.metadata
        assert "first_draft" not in result.metadata


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = DonorEligibilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "donation_type",
            "screening_gap_flags",
            "testing_gap_flags",
            "ineligible_release_flags",
            "donor_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["donor_checklist"][0] == "[OWNER: Quality Assurance / Tissue-Safety (Donor-Eligibility) Officer]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = DonorEligibilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        below_critique = (
            "SCREENING-GAP FLAGS: None detected\n"
            "TESTING-GAP FLAGS: None detected\n"
            "INELIGIBLE-RELEASE FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        wf = DonorEligibilityWorkflow(
            executor=FakeExecutor(["d1", "d2", "d3"]),
            reviewer=FakeReviewer([
                make_review(7.9, approved=False, critique=below_critique),
                make_review(7.9, approved=False, critique=below_critique),
                make_review(7.9, approved=False, critique=below_critique),
            ]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
