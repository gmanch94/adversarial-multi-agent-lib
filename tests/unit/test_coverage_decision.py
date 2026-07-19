"""Unit tests for CoverageDecisionWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.pc.workflows.coverage_decision import (
    CoverageDecisionRequest,
    CoverageDecisionWorkflow,
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
    score: float,
    *,
    approved: bool,
    critique: str = "",
    suggestions: list[str] | None = None,
) -> ReviewResult:
    return ReviewResult(
        score=score,
        critique=critique,
        suggestions=suggestions or [],
        approved=approved,
    )


def make_request(**kwargs: Any) -> CoverageDecisionRequest:
    defaults: dict[str, Any] = dict(
        claim_summary="Restaurant BI claim 2026; civil-authority closure for norovirus.",
        policy_wording=(
            "CP 00 30: BI requires direct physical loss. CP 01 40: virus exclusion."
        ),
        factual_disputes="Insurer says virus exclusion; insured says civil-authority extension.",
        state_law="Ohio. Sup. Ct. has not addressed virus-exclusion + civil-authority directly.",
        bad_faith_exposure="Initial ROR 45 days late. Surplus-lines. No prior denials.",
        proposed_decision="DENIAL based on virus exclusion + no direct physical loss.",
    )
    defaults.update(kwargs)
    return CoverageDecisionRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> CoverageDecisionWorkflow:
    return CoverageDecisionWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Claim Summary
Restaurant BI claim, Hamilton County OH, civil-authority closure following norovirus.

## Applicable Wording
CP 00 30 controls; CP 01 40 virus exclusion applies if virus is the proximate cause.

## Factual-Dispute Analysis
Disputed: proximate cause (closure order vs virus). Burden: insurer on exclusion.

## Coverage Conclusion
Partial coverage with ROR pending Ohio sup-ct guidance on single-premises virus claims.

## Case-Law Authority
Santo's Italian Cafe (6th Cir 2021): pandemic-era ruling, distinguishable on single-premises facts.

## Bad-Faith Screen
45-day ROR delay flagged; recommend immediate ROR letter + investigation.

## Next Actions
ROR within 7 days; coverage-counsel review on partial; calendar 21-day Ohio response window.

## Evidence Gaps
Health-dept order text not on file; need verbatim copy for civil-authority analysis.

## Claims
[Source: policy_wording] CP 00 30 requires direct physical loss for BI coverage.
[Source: state_law] Santo's Italian Cafe is distinguishable on single-premises facts.
[Source: bad_faith_exposure] ROR was issued 45 days after claim — outside Ohio 21-day window.
"""


_CLEAN_CRITIQUE = """\
Sound analysis.

Overall score: 8.5/10
Key issues:
- Health-dept order text gap should be cured before final decision.

WORDING FLAGS: None detected
CASE-LAW FLAGS: None detected
REVIEWER VETO: None
"""


class TestCoverageConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert "veto_reason" not in result.metadata

    @pytest.mark.asyncio
    async def test_does_not_converge_when_wording_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: clause paraphrased\n"
            "WORDING FLAGS:\n- CP 01 40 quoted incorrectly; missing 'microorganism' clause\n"
            "CASE-LAW FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        # Exact: proves the sibling CASE-LAW / REVIEWER VETO lines that follow are
        # not slurped into this list (H-IND-1 class).
        assert result.metadata["wording_flags"] == [
            "CP 01 40 quoted incorrectly; missing 'microorganism' clause"
        ]

    @pytest.mark.asyncio
    async def test_does_not_converge_when_case_law_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: wrong jurisdiction\n"
            "WORDING FLAGS: None detected\n"
            "CASE-LAW FLAGS:\n- Santo's is 6th Cir applying Iowa law, not Ohio\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert result.metadata["case_law_flags"] == [
            "Santo's is 6th Cir applying Iowa law, not Ohio"
        ]


class TestCoverageVeto:
    @pytest.mark.asyncio
    async def test_veto_halts_immediately_with_high_score(
        self, tmp_path: Path
    ) -> None:
        veto_critique = (
            "Overall score: 9.0/10\nKey issues: structural\n"
            "WORDING FLAGS: None detected\nCASE-LAW FLAGS: None detected\n"
            "REVIEWER VETO: Bad-faith pattern (45-day ROR delay + surplus-lines + "
            "plaintiff signal); proposed denial would create extra-contractual exposure."
        )
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(9.0, approved=True, critique=veto_critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert "veto_reason" in result.metadata
        assert "Bad-faith" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert _VETO_BANNER in result.output

    @pytest.mark.asyncio
    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "veto_reason" not in result.metadata


class TestCoverageOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered_into_ledger(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestCoverageDecisionRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        for fragment in [
            "Claim summary:",
            "Policy wording:",
            "Factual disputes:",
            "State law:",
            "Bad-faith exposure:",
            "Proposed decision:",
        ]:
            assert fragment in text
