"""Unit tests for CommercialUnderwritingWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.pc.workflows.commercial_underwriting import (
    CommercialUnderwritingRequest,
    CommercialUnderwritingWorkflow,
    _DISCLAIMER,
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


def make_request(**kwargs: Any) -> CommercialUnderwritingRequest:
    defaults: dict[str, Any] = dict(
        insured_summary="Mid-market structural-steel fabricator; NAICS 332312; $48M revenue.",
        prior_loss_history="5yr GL incurred $1.42M / 7 claims; two > $250k; severity trend rising.",
        hazard_grade="HIGH: hot work at customer sites, falling-object, structural-fit liability.",
        requested_coverage="GL $1M/$2M; products-comp-ops $2M agg; umbrella $10M.",
        proposed_terms="GL premium $96.5k; SIR $25k; blanket AI + primary-noncontrib endorsements.",
        regulatory_context="Admitted PA OH WV NY; ISO LCM 1.18; ±10% filed deviation available.",
        capacity_constraint="LOB agg 42M/50M used; treaty cession within net retention.",
    )
    defaults.update(kwargs)
    return CommercialUnderwritingRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path,
    executor: FakeExecutor, reviewer: FakeReviewer,
) -> CommercialUnderwritingWorkflow:
    return CommercialUnderwritingWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Insured Summary
Ironclad Fabrication; structural-steel custom fab; 122 employees; $48M revenue.

## Hazard Grade
HIGH; hot-work + customer-site installation; products-comp-ops tail.

## Loss-History Analysis
7 claims / 5 yrs; frequency stable; severity rising. Two large losses at customer sites.

## Proposed Premium and Terms
GL $1M/$2M; premium $96.5k computed as ISO_loss_cost × LCM 1.18 × frequency-debit 5%; SIR $25k.

## Exclusion Schedule
Contractors limitation + designated-premises restriction + hot-work-procedures endorsement.

## Capacity Check
LOB agg 42M/50M used; +$2M lands inside cap; treaty cession within $1M net retention.

## Coverage Coordination
Umbrella $10M attaches at $1M GL; primary-and-noncontributory blanket AI for customer-site work.

## Evidence Gaps
Customer-site hot-work procedures documentation not yet provided; condition-precedent.

## Claims
[Source: prior_loss_history] Severity trend has been rising over the 5-year window.
[Source: hazard_grade] Hot-work at customer sites is the dominant large-loss driver.
[Source: capacity_constraint] LOB aggregate has $8M headroom remaining after this bind.
"""


_CLEAN_CRITIQUE = """\
Bind is defensible.

Overall score: 8.2/10
Key issues:
- Customer-site hot-work procedures documentation should be condition-precedent.

LOSS-COST FLAGS: None detected
EXCLUSION FLAGS: None detected
CAPACITY FLAGS: None detected
"""


class TestUWConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.2, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1

    @pytest.mark.asyncio
    async def test_does_not_converge_when_loss_cost_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: under-priced\n"
            "LOSS-COST FLAGS:\n- Premium below ISO × LCM × 0.90 floor\n"
            "EXCLUSION FLAGS: None detected\n"
            "CAPACITY FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("below ISO" in f for f in result.metadata["loss_cost_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_exclusion_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: missing class-specific exclusion\n"
            "LOSS-COST FLAGS: None detected\n"
            "EXCLUSION FLAGS:\n- Absolute pollution exclusion missing for hot-work class\n"
            "CAPACITY FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("pollution" in f for f in result.metadata["exclusion_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_capacity_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: capacity breach\n"
            "LOSS-COST FLAGS: None detected\n"
            "EXCLUSION FLAGS: None detected\n"
            "CAPACITY FLAGS:\n- Bind pushes LOB aggregate above 95% utilisation\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("aggregate" in f for f in result.metadata["capacity_flags"])


class TestUWOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.2, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered_into_ledger(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.2, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestCommercialUnderwritingRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        for fragment in [
            "Insured summary:",
            "Prior loss history:",
            "Hazard grade:",
            "Requested coverage:",
            "Proposed terms:",
            "Regulatory context:",
            "Capacity constraint:",
        ]:
            assert fragment in text
