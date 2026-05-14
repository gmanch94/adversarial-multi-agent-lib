"""Unit tests for GigPlatformLiabilityWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.pc.workflows.gig_platform_liability import (
    GigPlatformLiabilityRequest,
    GigPlatformLiabilityWorkflow,
    _DISCLAIMER,
    _VETO_BANNER,
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


def make_result(
    score: float, *, approved: bool, critique: str = "",
    suggestions: list[str] | None = None,
) -> ReviewResult:
    return ReviewResult(
        score=score, critique=critique,
        suggestions=suggestions or [], approved=approved,
    )


def make_request(**kwargs: Any) -> GigPlatformLiabilityRequest:
    defaults: dict[str, Any] = dict(
        platform_summary="FixIt Now; skilled-trades dispatch CA/TX/FL; 4,800 1099 contractors; $148M GMV.",
        workforce_classification="All 1099; Prop 22 NOT applicable (skilled trades); Garcia CA class action pending.",
        coverage_stack="GL $5M/$10M; excess $25M; occ-acc $500k med-only; contingent auto $1M; EPLI $3M; NO reclass rider.",
        personal_policy_context="62% CA workers have commercial-auto endorsement; 'en-route' definition ambiguous.",
        state_regulatory_posture="CA AB5 ABC test; CA AG inquiry; TX common-law; FL § 627.748 TNC excludes trades.",
        pending_litigation="Garcia v FixIt (Alameda 2026-02; 1,950 class); PAGA notice; CA AG inquiry 2026-01.",
        proposed_bind_or_decision="GL +8%; EPLI +15%; occ-acc CA reduced to $300k; NO reclass rider; NO en-route bridge.",
    )
    defaults.update(kwargs)
    return GigPlatformLiabilityRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path,
    executor: FakeExecutor, reviewer: FakeReviewer,
) -> GigPlatformLiabilityWorkflow:
    return GigPlatformLiabilityWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Platform & Workforce Summary
FixIt Now; multi-state skilled-trades dispatch (CA/TX/FL); 4,800 1099 contractors.

## Worker-Classification Posture
CA: AB5 ABC-test prong-B disputed; Garcia class action pending. TX/FL: common-law contractor.

## Coverage Stack
GL/excess/contingent-auto/EPLI/occ-acc; NO reclass rider; CA occ-acc not WC-substitute valid.

## Personal-Policy Intersection
62% CA worker commercial-auto compliance; en-route timestamp ambiguous; bridge endorsement gap.

## Regulatory Posture
CA AB5 + AG inquiry; TX common-law (no TNC for trades); FL § 627.748 excludes trades; FL DEO UI risk.

## Proposed Bind / Decision
Renewal +8% GL; +15% EPLI; occ-acc CA $300k; CP: 85% CA worker compliance by effective date.

## Class-Action / Retroactive Exposure
Garcia putative class 1,950 CA workers; PAGA; AG inquiry; retroactive reclass exposure NOT rider-bridged.

## Next Actions
Add retroactive-reclassification rider; en-route bridge endorsement; CA AG monitoring.

## Evidence Gaps
NLRB joint-employer determination roadmap not yet on file for skilled-trades segment.

## Claims
[Source: state_regulatory_posture] Prop 22 does NOT extend to skilled-trades platforms.
[Source: pending_litigation] Garcia v FixIt is a putative class of 1,950 CA contractors.
[Source: personal_policy_context] Only 62% of CA workers carry valid commercial-auto endorsement.
"""


_CLEAN_CRITIQUE = """\
Analysis is defensible with stated conditions.

Overall score: 8.0/10
Key issues:
- NLRB roadmap should be on file for skilled-trades context.

CLASSIFICATION FLAGS: None detected
COVERAGE-GAP FLAGS: None detected
REGULATORY-PATCHWORK FLAGS: None detected
REVIEWER VETO: None
"""


class TestGigConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    @pytest.mark.asyncio
    async def test_does_not_converge_when_classification_flags(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.0/10\nKey issues: ABC prong B fails\n"
            "CLASSIFICATION FLAGS:\n- AB5 prong B fails — trades work IS FixIt's usual course\n"
            "COVERAGE-GAP FLAGS: None detected\n"
            "REGULATORY-PATCHWORK FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("prong B" in f for f in result.metadata["classification_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_coverage_gap_flags(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: en-route gap\n"
            "CLASSIFICATION FLAGS: None detected\n"
            "COVERAGE-GAP FLAGS:\n- En-route timestamp ambiguity creates uninsured window\n"
            "REGULATORY-PATCHWORK FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("En-route" in f for f in result.metadata["coverage_gap_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_regulatory_patchwork_flags(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: FL DEO posture missing\n"
            "CLASSIFICATION FLAGS: None detected\n"
            "COVERAGE-GAP FLAGS: None detected\n"
            "REGULATORY-PATCHWORK FLAGS:\n- FL DEO UI back-tax risk not priced\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("FL DEO" in f for f in result.metadata["regulatory_patchwork_flags"])


class TestGigVeto:
    @pytest.mark.asyncio
    async def test_veto_halts_immediately_with_high_score(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 8.5/10\nKey issues: structural\n"
            "CLASSIFICATION FLAGS: None detected\n"
            "COVERAGE-GAP FLAGS: None detected\n"
            "REGULATORY-PATCHWORK FLAGS: None detected\n"
            "REVIEWER VETO: Proposed bind would only survive a CA AB5 audit by accident; "
            "platform operating model fails ABC prong B and retroactive reclass exposure "
            "is unpriced — escalate to platform-liability counsel."
        )
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=veto_critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert "veto_reason" in result.metadata
        assert "AB5" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert _VETO_BANNER in result.output

    @pytest.mark.asyncio
    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "veto_reason" not in result.metadata


class TestGigOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered_into_ledger(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestGigPlatformLiabilityRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        for fragment in [
            "Platform summary:",
            "Workforce classification:",
            "Coverage stack:",
            "Personal-policy context:",
            "State regulatory posture:",
            "Pending litigation:",
            "Proposed bind / decision:",
        ]:
            assert fragment in text
