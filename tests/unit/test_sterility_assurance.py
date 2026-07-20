"""Unit tests for SterilityAssuranceWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-4): clean convergence, exact-flag non-convergence,
sibling-header stop, veto halt with first_draft, no-veto, metadata, disclaimer,
threshold boundary.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.sterility_assurance import (
    SterilityAssuranceRequest,
    SterilityAssuranceWorkflow,
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


def make_request(**kwargs: Any) -> SterilityAssuranceRequest:
    defaults: dict[str, Any] = dict(
        product_description="A single-use surgical device in a porous nonwoven / "
                           "film sterile-barrier pouch.",
        sterilization_method="Ethylene oxide (EO); chosen for material "
                            "compatibility with the polymer housing.",
        sal_target="10^-6.",
        bioburden_summary="Routine bioburden trending near the validated limit "
                         "over the last four lots.",
        validation_summary="Half-cycle validation completed; predates a recent "
                          "housing-material change.",
        packaging_barrier="Seal-strength and dye-penetration validation on file.",
        routine_control_summary="Biological indicators and residual EO testing "
                               "on every load.",
        revalidation_status="Annual revalidation due; last performed 13 months ago.",
    )
    defaults.update(kwargs)
    return SterilityAssuranceRequest(**defaults)


def clean_critique() -> str:
    return (
        "SAL demonstrated; bioburden controlled; validation current.\n\n"
        "Overall score: 8.4/10\n"
        "Key issues:\n- Schedule the annual revalidation\n"
        "SAL FLAGS: None detected\n"
        "BIOBURDEN FLAGS: None detected\n"
        "VALIDATION-GAP FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## SAL demonstration
The 10^-6 SAL is demonstrated by the current half-cycle validation and routine
controls.

## Bioburden control
Routine bioburden is within the validated limit.

## Validation completeness
All validation and sterile-barrier elements are current.

## Routine control and disposition
Routine control is adequate; product may be released as sterile.

## Claims
[Source: sterilization_method] EO was selected for material compatibility.
[Source: sal_target] The claimed SAL is 10^-6.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Sterilization method:",
            "SAL target:",
            "Bioburden summary:",
            "Validation summary:",
            "Packaging barrier:",
            "Routine control summary:",
            "Revalidation status:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(bioburden_summary=oversized).to_prompt_text()
        section = text.split("Bioburden summary:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = SterilityAssuranceWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.4, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_bioburden_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: bioburden trend\n"
            "SAL FLAGS: None detected\n"
            "BIOBURDEN FLAGS:\n"
            "- Routine bioburden trending above the validated limit for the EO cycle\n"
            "VALIDATION-GAP FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = SterilityAssuranceWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["bioburden_flags"] == [
            "Routine bioburden trending above the validated limit for the EO cycle"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "SAL FLAGS: None detected\n"
            "BIOBURDEN FLAGS:\n"
            "- Bioburden near the validated limit\n"
            "RECOMMENDATION: requalify the cycle\n"
            "VALIDATION-GAP FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = SterilityAssuranceWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["bioburden_flags"] == ["Bioburden near the validated limit"]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: sterile release without a demonstrated SAL\n"
            "SAL FLAGS: None detected\n"
            "BIOBURDEN FLAGS: None detected\n"
            "VALIDATION-GAP FLAGS: None detected\n"
            "REVIEWER VETO: Product is proposed for release as sterile while the "
            "claimed SAL is not demonstrated and bioburden exceeds the validated "
            "limit; it must not be released as sterile. Escalate to Microbiology "
            "Quality."
        )
        config = make_config(tmp_path)
        wf = SterilityAssuranceWorkflow(
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
        assert "released" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = SterilityAssuranceWorkflow(
            executor=FakeExecutor(responses=["draft"]),
            reviewer=FakeReviewer(results=[make_review(8.4, approved=True, critique=clean_critique())]),
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
        wf = SterilityAssuranceWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.4, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "sal_flags",
            "bioburden_flags",
            "validation_gap_flags",
            "sterility_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["sterility_checklist"][0] == (
            "[OWNER: Sterilization / Microbiology Quality]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = SterilityAssuranceWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.4, approved=True, critique=clean_critique())]),
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
            "SAL FLAGS: None detected\n"
            "BIOBURDEN FLAGS: None detected\n"
            "VALIDATION-GAP FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = SterilityAssuranceWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
