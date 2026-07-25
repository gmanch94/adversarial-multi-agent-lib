"""Unit tests for CGTPotencyAssayWorkflow (Lifesciences CGT · veto) — no live API.

Veto + triple-flag (D-LIFESCI-8). Mirrors the se510k veto shape.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.cgt_potency_assay import (
    CGTPotencyAssayWorkflow,
    PotencyAssayRequest,
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


def make_request(**kwargs: Any) -> PotencyAssayRequest:
    defaults: dict[str, Any] = dict(
        product_description="An autologous CAR-T cell therapy.",
        mechanism_of_action=(
            "CAR-mediated recognition of a tumour-associated antigen driving T-cell "
            "cytotoxicity and cytokine release."
        ),
        potency_assay_description=(
            "An antigen-specific cytotoxicity assay measuring target-cell killing, "
            "with an IFN-gamma release co-readout."
        ),
        moa_linkage_rationale=(
            "Cytotoxicity and IFN-gamma release directly reflect the CAR-mediated "
            "killing mechanism."
        ),
        assay_validation_summary=(
            "Validated for accuracy, precision, specificity, and range; "
            "stability-indicating over the shelf life."
        ),
        acceptance_criteria="Specific lysis >= 30% at the defined E:T ratio.",
        lot_release_claim="The product meets the potency specification for release.",
        surrogate_or_matrix_justification="No surrogate used; primary killing readout.",
        stability_indicating_evidence=(
            "Potency declines measurably on forced degradation, confirming "
            "stability-indicating behaviour."
        ),
    )
    defaults.update(kwargs)
    return PotencyAssayRequest(**defaults)


def clean_critique() -> str:
    return (
        "MoA-linked; claim supported; validation adequate.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm the E:T ratio matches the clinical dose\n"
        "MOA-LINKAGE FLAGS: None detected\n"
        "LOT-RELEASE-CLAIM FLAGS: None detected\n"
        "ASSAY-VALIDATION FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Mechanism-of-action linkage
The cytotoxicity readout reflects CAR-mediated killing; IFN-gamma corroborates.

## Lot-release claim
The specific-lysis criterion supports the release claim.

## Assay validation
Validated for accuracy, precision, specificity, range; stability-indicating.

## Surrogate / matrix justification
No surrogate used.

## Release-adequacy conclusion
The potency assay is adequate to support lot release.

## Claims
[Source: acceptance_criteria] Specific lysis >= 30% at the defined E:T ratio.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Mechanism of action:",
            "Potency assay description:",
            "MoA linkage rationale:",
            "Assay validation summary:",
            "Acceptance criteria:",
            "Lot-release claim:",
            "Surrogate / matrix justification:",
            "Stability-indicating evidence:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(mechanism_of_action=oversized).to_prompt_text()
        section = text.split("Mechanism of action:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTPotencyAssayWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_moa_linkage_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: readout not MoA-linked\n"
            "MOA-LINKAGE FLAGS:\n"
            "- Viability readout is not linked to the cytotoxic mechanism of action\n"
            "LOT-RELEASE-CLAIM FLAGS: None detected\n"
            "ASSAY-VALIDATION FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = CGTPotencyAssayWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["moa_linkage_flags"] == [
            "Viability readout is not linked to the cytotoxic mechanism of action"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: readout not MoA-linked\n"
            "MOA-LINKAGE FLAGS:\n"
            "- Viability readout is not linked to the cytotoxic mechanism of action\n"
            "RECOMMENDATION: adopt an antigen-specific killing readout\n"
            "LOT-RELEASE-CLAIM FLAGS: None detected\n"
            "ASSAY-VALIDATION FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = CGTPotencyAssayWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["moa_linkage_flags"] == [
            "Viability readout is not linked to the cytotoxic mechanism of action"
        ]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: assay does not measure activity\n"
            "MOA-LINKAGE FLAGS: None detected\n"
            "LOT-RELEASE-CLAIM FLAGS: None detected\n"
            "ASSAY-VALIDATION FLAGS: None detected\n"
            "REVIEWER VETO: The potency assay measures total viable cells, not "
            "antigen-specific killing; it does not measure clinical activity. "
            "Releasing on it risks releasing product without demonstrated potency. "
            "Requalify with an MoA-linked assay before release."
        )
        config = make_config(tmp_path)
        wf = CGTPotencyAssayWorkflow(
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
        assert "does not measure clinical activity" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTPotencyAssayWorkflow(
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
        wf = CGTPotencyAssayWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "moa_linkage_flags",
            "lot_release_claim_flags",
            "assay_validation_flags",
            "potency_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["potency_checklist"][0] == "[OWNER: CMC / Analytical Development + Quality Engineering]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTPotencyAssayWorkflow(
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
            "MOA-LINKAGE FLAGS: None detected\n"
            "LOT-RELEASE-CLAIM FLAGS: None detected\n"
            "ASSAY-VALIDATION FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        wf = CGTPotencyAssayWorkflow(
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
