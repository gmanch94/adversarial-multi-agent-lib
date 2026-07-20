"""Unit tests for MedicalInformationResponseWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-4) + D-LIFESCI-2 boundary vs the promotional
off-label review: clean convergence, exact-flag non-convergence, sibling-header
stop, veto halt with first_draft, no-veto, metadata, disclaimer, threshold
boundary, module-docstring boundary statement.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.medical_information_response import (
    MedicalInfoRequest,
    MedicalInformationResponseWorkflow,
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


def make_request(**kwargs: Any) -> MedicalInfoRequest:
    defaults: dict[str, Any] = dict(
        product_description="An approved oral therapy for an adult indication.",
        inquiry_summary="An HCP asks about dosing the product in a pediatric "
                       "patient (an off-label population).",
        inquiry_source="Unsolicited inquiry from a treating physician.",
        on_off_label_status="Off-label (pediatric use is not in the label).",
        proposed_response="A drafted response summarizing the available pediatric "
                        "data and its limitations.",
        evidence_cited="Two small observational case series and a review article.",
        balance_summary="Efficacy and the known hepatic risk with monitoring are "
                       "both presented.",
        promotional_review_status="Drafted for MLR review; intended to be "
                                "non-promotional and reactive.",
    )
    defaults.update(kwargs)
    return MedicalInfoRequest(**defaults)


def clean_critique() -> str:
    return (
        "Reactive, balanced, and evidence-calibrated.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Add the citation for the review article\n"
        "OFF-LABEL FLAGS: None detected\n"
        "BALANCE FLAGS: None detected\n"
        "EVIDENCE-LEVEL FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Off-label boundary
The response neutrally summarizes the pediatric data in answer to the specific
question; it does not recommend the off-label use.

## Fair balance
Efficacy is presented alongside the known hepatic risk and monitoring requirement.

## Evidence calibration
Claims are calibrated to the observational nature of the evidence.

## Responsiveness and disposition
The response answers the question and may be sent subject to MLR. No adverse event
is present.

## Claims
[Source: inquiry_summary] The question concerns pediatric dosing.
[Source: balance_summary] The hepatic risk is presented with monitoring.
"""


def test_module_docstring_states_promotional_boundary() -> None:
    import adv_multi_agent.lifesciences.workflows.medical_information_response as mod
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "distinct from" in doc and "promotionalofflabelreview" in doc.replace(" ", "")


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Inquiry summary:",
            "Inquiry source:",
            "On/off-label status:",
            "Proposed response:",
            "Evidence cited:",
            "Balance summary:",
            "Promotional review status:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(inquiry_summary=oversized).to_prompt_text()
        section = text.split("Inquiry summary:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = MedicalInformationResponseWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_balance_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: missing risk balance\n"
            "OFF-LABEL FLAGS: None detected\n"
            "BALANCE FLAGS:\n"
            "- Efficacy summary omits the known hepatic risk and monitoring requirement\n"
            "EVIDENCE-LEVEL FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = MedicalInformationResponseWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["balance_flags"] == [
            "Efficacy summary omits the known hepatic risk and monitoring requirement"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "OFF-LABEL FLAGS: None detected\n"
            "BALANCE FLAGS:\n"
            "- Risk not presented with efficacy\n"
            "RECOMMENDATION: add the boxed-warning language\n"
            "EVIDENCE-LEVEL FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = MedicalInformationResponseWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["balance_flags"] == ["Risk not presented with efficacy"]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: promotes an off-label use\n"
            "OFF-LABEL FLAGS: None detected\n"
            "BALANCE FLAGS: None detected\n"
            "EVIDENCE-LEVEL FLAGS: None detected\n"
            "REVIEWER VETO: The drafted response recommends an off-label pediatric "
            "regimen rather than neutrally summarizing the evidence; it promotes an "
            "unapproved use and must not be sent. Escalate to Medical Affairs."
        )
        config = make_config(tmp_path)
        wf = MedicalInformationResponseWorkflow(
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
        assert "sent" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = MedicalInformationResponseWorkflow(
            executor=FakeExecutor(responses=["draft"]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert "veto_reason" not in result.metadata
        assert "vetoed" not in result.metadata


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = MedicalInformationResponseWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "off_label_flags",
            "balance_flags",
            "evidence_level_flags",
            "medinfo_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["medinfo_checklist"][0] == (
            "[OWNER: Medical Information / Medical Affairs]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = MedicalInformationResponseWorkflow(
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
        executor = FakeExecutor(["d1", "d2", "d3"])
        below_critique = (
            "OFF-LABEL FLAGS: None detected\n"
            "BALANCE FLAGS: None detected\n"
            "EVIDENCE-LEVEL FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = MedicalInformationResponseWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
