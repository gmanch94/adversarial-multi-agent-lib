"""Unit tests for BiosimilarComparabilityWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-4):
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when analytical-similarity flags present (exact == assertion)
- sibling-header stop (trailing RECOMMENDATION: not slurped)
- veto halts loop with first_draft preserved
- no veto when directive is None
- all metadata keys present on clean run
- disclaimer in output on clean run
- threshold boundary
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.biosimilar_comparability import (
    BiosimilarComparabilityRequest,
    BiosimilarComparabilityWorkflow,
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


def make_request(**kwargs: Any) -> BiosimilarComparabilityRequest:
    defaults: dict[str, Any] = dict(
        product_description="A proposed biosimilar monoclonal antibody referencing "
                           "an approved oncology reference product.",
        analytical_similarity_summary="Primary sequence identical; higher-order "
                                     "structure comparable; glycosylation profile "
                                     "assessed.",
        quality_attributes="CQAs: glycosylation (high risk), charge variants, "
                          "aggregation, potency.",
        pk_pd_summary="Single-dose PK crossover met the equivalence margins.",
        clinical_comparability_summary="Comparative efficacy and immunogenicity "
                                     "study in one indication showed no clinically "
                                     "meaningful difference.",
        residual_uncertainty="Caller states residual uncertainty is low after "
                            "analytical and clinical data.",
        bridging_summary="Bridged across two reference-product sourcing regions.",
        extrapolation_indications="Extrapolation to all reference-product "
                                "indications requested.",
    )
    defaults.update(kwargs)
    return BiosimilarComparabilityRequest(**defaults)


def clean_critique() -> str:
    return (
        "Analytical similarity demonstrated; residual uncertainty resolved.\n\n"
        "Overall score: 8.6/10\n"
        "Key issues:\n- Confirm the charge-variant range justification\n"
        "ANALYTICAL-SIMILARITY FLAGS: None detected\n"
        "RESIDUAL-UNCERTAINTY FLAGS: None detected\n"
        "BRIDGING FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Analytical-similarity summary
Every critical quality attribute, including glycosylation, is within the
justified reference range.

## Residual-uncertainty assessment
Residual uncertainty is low and resolved by the PK and clinical data.

## Bridging and extrapolation
Bridging across sourcing regions is justified; extrapolation is supported.

## Totality-of-evidence conclusion
The proposed product is biosimilar to the reference.

## Claims
[Source: quality_attributes] Glycosylation is a high-risk CQA.
[Source: analytical_similarity_summary] Higher-order structure is comparable.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Analytical similarity summary:",
            "Quality attributes:",
            "PK/PD summary:",
            "Clinical comparability summary:",
            "Residual uncertainty:",
            "Bridging summary:",
            "Extrapolation indications:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(analytical_similarity_summary=oversized).to_prompt_text()
        section = text.split("Analytical similarity summary:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = BiosimilarComparabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.6, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_analytical_similarity_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: glycosylation out of range\n"
            "ANALYTICAL-SIMILARITY FLAGS:\n"
            "- Glycosylation attribute falls outside the reference product range\n"
            "RESIDUAL-UNCERTAINTY FLAGS: None detected\n"
            "BRIDGING FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = BiosimilarComparabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["analytical_similarity_flags"] == [
            "Glycosylation attribute falls outside the reference product range"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "ANALYTICAL-SIMILARITY FLAGS:\n"
            "- Glycosylation out of range\n"
            "RECOMMENDATION: run an additional characterization assay\n"
            "RESIDUAL-UNCERTAINTY FLAGS: None detected\n"
            "BRIDGING FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = BiosimilarComparabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["analytical_similarity_flags"] == ["Glycosylation out of range"]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: biosimilarity concluded despite an unresolved CQA gap\n"
            "ANALYTICAL-SIMILARITY FLAGS: None detected\n"
            "RESIDUAL-UNCERTAINTY FLAGS: None detected\n"
            "BRIDGING FLAGS: None detected\n"
            "REVIEWER VETO: A biosimilarity conclusion is asserted while a "
            "glycosylation critical quality attribute is not analytically similar "
            "and the residual uncertainty is unresolved; biosimilarity must not be "
            "concluded. Escalate to Regulatory Affairs."
        )
        config = make_config(tmp_path)
        wf = BiosimilarComparabilityWorkflow(
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
        assert "concluded" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = BiosimilarComparabilityWorkflow(
            executor=FakeExecutor(responses=["draft"]),
            reviewer=FakeReviewer(results=[make_review(8.6, approved=True, critique=clean_critique())]),
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
        wf = BiosimilarComparabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.6, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "analytical_similarity_flags",
            "residual_uncertainty_flags",
            "bridging_flags",
            "biosimilar_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["biosimilar_checklist"][0] == (
            "[OWNER: Biosimilar Development / Regulatory Affairs]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = BiosimilarComparabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.6, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    """Zero flags + no veto but approved=False (score below threshold) must not converge."""

    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        below_critique = (
            "ANALYTICAL-SIMILARITY FLAGS: None detected\n"
            "RESIDUAL-UNCERTAINTY FLAGS: None detected\n"
            "BRIDGING FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = BiosimilarComparabilityWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
