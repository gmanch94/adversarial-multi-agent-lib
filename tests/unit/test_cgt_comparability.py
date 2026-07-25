"""Unit tests for CGTComparabilityWorkflow (Lifesciences CGT · veto) — no live API.

Veto + triple-flag (D-LIFESCI-6). Mirrors the se510k veto shape.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.cgt_comparability import (
    CGTComparabilityWorkflow,
    ComparabilityRequest,
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


def make_request(**kwargs: Any) -> ComparabilityRequest:
    defaults: dict[str, Any] = dict(
        product_description="An autologous gene-modified cell therapy.",
        change_description=(
            "A change of the lentiviral vector supplier and a two-fold scale-up of "
            "the transduction step."
        ),
        pre_change_process_summary=(
            "Vector from supplier A; transduction at the original scale; potency and "
            "VCN within range."
        ),
        post_change_process_summary=(
            "Vector from supplier B; transduction at two-fold scale; process "
            "otherwise unchanged."
        ),
        analytical_comparability_data=(
            "Identity, purity, VCN, and potency compared side-by-side across three "
            "post-change lots; all within the pre-change ranges."
        ),
        quality_attribute_panel="Identity, purity, potency, VCN, sterility, viability.",
        clinical_bridging_plan=(
            "No clinical bridge proposed; analytical comparability considered "
            "sufficient given the covered CQAs."
        ),
        risk_assessment_summary=(
            "Risk assessed as low; the change does not alter the transgene or the "
            "cell type."
        ),
    )
    defaults.update(kwargs)
    return ComparabilityRequest(**defaults)


def clean_critique() -> str:
    return (
        "CQAs covered; analytical panel sufficient; no residual uncertainty.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm supplier-B vector genetic identity\n"
        "PROCESS-DELTA FLAGS: None detected\n"
        "ANALYTICAL-GAP FLAGS: None detected\n"
        "CLINICAL-BRIDGE FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Process-change impact
Vector supplier change and scale-up assessed; VCN and potency covered.

## Analytical comparability
Three post-change lots within pre-change ranges across the panel.

## Clinical bridging
No residual uncertainty; analytical comparability sufficient.

## Risk assessment
Low risk; transgene and cell type unchanged.

## Comparability conclusion
The post-change product is comparable.

## Claims
[Source: analytical_comparability_data] Three lots within pre-change ranges.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Change description:",
            "Pre-change process summary:",
            "Post-change process summary:",
            "Analytical comparability data:",
            "Quality-attribute panel:",
            "Clinical bridging plan:",
            "Risk assessment summary:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(change_description=oversized).to_prompt_text()
        section = text.split("Change description:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTComparabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_process_delta_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: vector change uncovered\n"
            "PROCESS-DELTA FLAGS:\n"
            "- Supplier-B vector integration profile is not compared to supplier A\n"
            "ANALYTICAL-GAP FLAGS: None detected\n"
            "CLINICAL-BRIDGE FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = CGTComparabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["process_delta_flags"] == [
            "Supplier-B vector integration profile is not compared to supplier A"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: vector change uncovered\n"
            "PROCESS-DELTA FLAGS:\n"
            "- Supplier-B vector integration profile is not compared to supplier A\n"
            "RECOMMENDATION: run an integration-site comparison\n"
            "ANALYTICAL-GAP FLAGS: None detected\n"
            "CLINICAL-BRIDGE FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = CGTComparabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["process_delta_flags"] == [
            "Supplier-B vector integration profile is not compared to supplier A"
        ]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: different product\n"
            "PROCESS-DELTA FLAGS: None detected\n"
            "ANALYTICAL-GAP FLAGS: None detected\n"
            "CLINICAL-BRIDGE FLAGS: None detected\n"
            "REVIEWER VETO: The new vector alters the integration profile and the "
            "post-change potency distribution shifts materially; this is a materially "
            "different product. Treating it as comparable without new clinical data "
            "is not supportable. Generate bridging clinical data before the change."
        )
        config = make_config(tmp_path)
        wf = CGTComparabilityWorkflow(
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
        assert "materially different product" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTComparabilityWorkflow(
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
        wf = CGTComparabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "process_delta_flags",
            "analytical_gap_flags",
            "clinical_bridge_flags",
            "comparability_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["comparability_checklist"][0] == "[OWNER: Regulatory Affairs + CMC Lead]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTComparabilityWorkflow(
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
            "PROCESS-DELTA FLAGS: None detected\n"
            "ANALYTICAL-GAP FLAGS: None detected\n"
            "CLINICAL-BRIDGE FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        wf = CGTComparabilityWorkflow(
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
