"""Unit tests for PromotionalOffLabelReviewWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-3). Mirrors test_substantial_equivalence_510k.py:
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when off-label flags present (exact == assertion)
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
from adv_multi_agent.lifesciences.workflows.promotional_off_label_review import (
    PromotionalOffLabelReviewWorkflow,
    PromoReviewRequest,
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


def make_request(**kwargs: Any) -> PromoReviewRequest:
    defaults: dict[str, Any] = dict(
        material_type=(
            "A healthcare-professional visual aid (leave-behind detail piece) for "
            "an established oral small-molecule therapy."
        ),
        target_audience="Prescribing physicians (specialist HCP audience).",
        promo_claims=(
            "Claim 1: reduces symptom burden within the approved indication. "
            "Claim 2: well tolerated versus the standard of care."
        ),
        approved_labeling_reference=(
            "Approved labeling: indicated for adults with the on-label condition; "
            "boxed warning for a known adverse reaction; contraindications listed."
        ),
        cited_references=(
            "One pivotal randomised controlled trial and one post-hoc analysis."
        ),
        risk_information_present=(
            "Important safety information appears with comparable prominence to the "
            "benefit claims, including the boxed warning."
        ),
        comparative_claims=(
            "One tolerability comparative claim supported by a head-to-head trial."
        ),
    )
    defaults.update(kwargs)
    return PromoReviewRequest(**defaults)


def clean_critique() -> str:
    return (
        "All claims on-label; fair balance intact; each claim substantiated.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm the head-to-head trial supports the tolerability claim\n"
        "OFF-LABEL FLAGS: None detected\n"
        "FAIR-BALANCE FLAGS: None detected\n"
        "SUBSTANTIATION FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Claim-by-claim label check
Every claim maps to the approved indication and population. No off-label use.

## Fair-balance assessment
Important safety information is comparably prominent to the benefit claims,
including the boxed warning.

## Substantiation and references
Each efficacy claim is backed by the pivotal RCT; the comparative claim by a
head-to-head trial.

## Comparative-claim check
The single tolerability comparative claim is adequately supported.

## Redline recommendations
No redlines required; material is within the approved label.

## Claims
[Source: promo_claims] All claims are within the approved indication.
[Source: risk_information_present] Risk information is comparably prominent.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Material type:",
            "Target audience:",
            "Promotional claims:",
            "Approved labeling reference:",
            "Cited references:",
            "Risk information present:",
            "Comparative claims:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(promo_claims=oversized).to_prompt_text()
        section = text.split("Promotional claims:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = PromotionalOffLabelReviewWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_off_label_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: a claim reaches beyond the approved population\n"
            "OFF-LABEL FLAGS:\n"
            "- Claim promotes use in a population outside the approved indication\n"
            "FAIR-BALANCE FLAGS: None detected\n"
            "SUBSTANTIATION FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = PromotionalOffLabelReviewWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["off_label_flags"] == [
            "Claim promotes use in a population outside the approved indication"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: a claim reaches beyond the approved population\n"
            "OFF-LABEL FLAGS:\n"
            "- Claim promotes use in a population outside the approved indication\n"
            "RECOMMENDATION: restrict the claim to the approved indication\n"
            "FAIR-BALANCE FLAGS: None detected\n"
            "SUBSTANTIATION FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = PromotionalOffLabelReviewWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["off_label_flags"] == [
            "Claim promotes use in a population outside the approved indication"
        ]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: off-label population claim with under-prominent risk\n"
            "OFF-LABEL FLAGS: None detected\n"
            "FAIR-BALANCE FLAGS: None detected\n"
            "SUBSTANTIATION FLAGS: None detected\n"
            "REVIEWER VETO: The material promotes use in a pediatric population "
            "outside the approved adult indication while the boxed warning is "
            "relegated to fine print. This would likely draw an FDA enforcement "
            "letter. Escalate to MLR; do not release the material."
        )
        config = make_config(tmp_path)
        wf = PromotionalOffLabelReviewWorkflow(
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
        assert "pediatric" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = PromotionalOffLabelReviewWorkflow(
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
        wf = PromotionalOffLabelReviewWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "material_type",
            "off_label_flags",
            "fair_balance_flags",
            "substantiation_flags",
            "promo_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["promo_checklist"][0] == (
            "[OWNER: MLR Committee (Medical + Legal + Regulatory)]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = PromotionalOffLabelReviewWorkflow(
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
    """L-HEALTH-3: zero flags + no veto but approved=False (score below threshold) must not converge."""

    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        below_critique = (
            "OFF-LABEL FLAGS: None detected\n"
            "FAIR-BALANCE FLAGS: None detected\n"
            "SUBSTANTIATION FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = PromotionalOffLabelReviewWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
