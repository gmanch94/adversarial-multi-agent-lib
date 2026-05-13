"""Unit tests for SupplierBriefWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.retail.workflows.supplier_brief import (
    SupplierBriefRequest,
    SupplierBriefWorkflow,
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


def make_request(**kwargs: Any) -> SupplierBriefRequest:
    defaults: dict[str, Any] = dict(
        supplier_name="Pacific Corrugated Co.",
        category="corrugated-packaging RSC-32ECT",
        current_terms="$0.84/box, net-45, MOQ 50k, lead 18d, 14mo remaining on 36mo deal",
        target_terms="$0.78/box, net-60, MOQ 75k, lead 14d, extend 24mo",
        volume_history="4.8M boxes TTM +6% YoY; forecast +6% next 12mo; sole-source",
        alternatives=(
            "Midwest Box Inc. — qualified, +4% landed, audited Q3 2025, "
            "capacity ~3.2M/yr (63% of volume). RegionalPak — unqualified, "
            "indicative -2%, audit ~4mo."
        ),
        cost_drivers=(
            "Containerboard index -3.4% YoY (corp feed 2026-04). Inland freight "
            "diesel +1.1% YoY. Labour est +2.5% YoY (regional CBA)."
        ),
        relationship_context=(
            "STRATEGIC supplier; sole-source on this SKU + 2 co-developed sustainable "
            "SKUs; joint innovation roadmap 2024; priority allocation during 2024 crunch."
        ),
        negotiation_constraints=(
            "ESG Tier-1 partner; volume shift counts against Scope-3 roadmap. "
            "Payment term > net-60 needs CFO. Walk-away on sole-source needs 90d "
            "continuity plan."
        ),
    )
    defaults.update(kwargs)
    return SupplierBriefRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> SupplierBriefWorkflow:
    return SupplierBriefWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## BATNA Assessment
Midwest Box Inc. is qualified (audited Q3 2025), landed cost +4% vs Pacific,
capacity ~3.2M/yr covering ~63% of volume — partial-coverage backup. RegionalPak
unqualified, indicative -2%, ~4mo audit cycle — not actionable inside the
negotiation window. Net: partial BATNA, weakened by single-source share.

## Cost-Floor Defence
Containerboard -3.4% YoY supports a price reduction. Diesel +1.1% and labour
+2.5% partially offset. Implied driver-weighted cost floor: roughly $0.80/box.
The ask at $0.78 is just below the implied floor; volume + term extension is
the offset (75k MOQ, +24mo term).

## Relationship Implications
Pacific is STRATEGIC. The price-cut tactic carries a multi-year cost: risk to
joint-innovation roadmap and to priority allocation in a future crunch. The
brief explicitly accepts this cost in exchange for the term extension and
ESG-roadmap continuity.

## Opening Offer + Landing Zone + Walk-Away
Opening: $0.74/box, net-60, MOQ 75k, +24mo. Landing zone: $0.78–$0.80, net-60,
MOQ 75k, +24mo. Walk-away: $0.82, net-45, no extension (above Midwest landed
+4% to preserve relationship).

## Concession Order
1. Drop MOQ ask back to 60k → demand confirmation of priority allocation.
2. Drop payment to net-45 → demand $0.77/box.
3. Drop term extension to 12mo → demand $0.76/box.

## Talking Points
- Cost-driver objection ("our labour is up"): containerboard outweighs at our
  volume; net driver-weighted move is down.
- Capacity objection ("Midwest cannot cover"): acknowledged; the volume +
  term offer is designed to keep Pacific as primary.
- Relationship appeal: term extension + ESG-roadmap continuity ARE the
  relationship signals; price cut is paired with multi-year commitment.

## Evidence Gaps
Pacific's actual labour cost movement is estimated; a current quote-back
would tighten the floor estimate.

## Claims
[Source: alternatives] Midwest Box Inc. is qualified at +4% landed, ~3.2M/yr capacity.
[Source: cost_drivers] Containerboard index -3.4% YoY per 2026-04 corporate feed.
[Source: relationship_context] Pacific is sole-source on this SKU plus 2 co-developed SKUs.
[Source: negotiation_constraints] Walk-away on sole-source requires 90-day continuity plan.
"""

_CLEAN_CRITIQUE = """\
Solid brief.

Overall score: 8.2/10
Key issues:
- Quote-back on Pacific's labour would tighten the floor estimate.

BATNA FLAGS: None detected
COST FLAGS: None detected
RELATIONSHIP FLAGS: None detected
"""


class TestSupplierConvergence:
    @pytest.mark.asyncio
    async def test_converges_when_no_flags(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.2, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1

    @pytest.mark.asyncio
    async def test_does_not_converge_when_batna_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.8/10\nKey issues: hand-waved alternative\n"
            "BATNA FLAGS:\n- Midwest capacity insufficient to anchor walk-away\n"
            "COST FLAGS: None detected\nRELATIONSHIP FLAGS: None detected"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.8, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Midwest" in f for f in result.metadata["batna_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_cost_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "BATNA FLAGS: None detected\n"
            "COST FLAGS:\n- Ask $0.78 below defensible floor $0.80\n"
            "RELATIONSHIP FLAGS: None detected\nOverall score: 7.0/10"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("below defensible" in f for f in result.metadata["cost_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_relationship_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "BATNA FLAGS: None detected\nCOST FLAGS: None detected\n"
            "RELATIONSHIP FLAGS:\n- Hardball on strategic supplier without acknowledging cost\n"
            "Overall score: 7.5/10"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.5, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Hardball" in f for f in result.metadata["relationship_flags"])


class TestSupplierOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.2, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_metadata_keys_present(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.2, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        for key in (
            "supplier_name",
            "category",
            "batna_flags",
            "cost_flags",
            "relationship_flags",
            "approver_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata

    @pytest.mark.asyncio
    async def test_claims_registered(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.2, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 4


class TestSupplierRequestPromptText:
    def test_renders_all_labels(self) -> None:
        text = make_request().to_prompt_text()
        for label in [
            "Supplier name:",
            "Category:",
            "Current terms:",
            "Target terms:",
            "Volume history:",
            "Alternatives:",
            "Cost drivers:",
            "Relationship context:",
            "Negotiation constraints:",
        ]:
            assert label in text


class TestBuildApproverChecklist:
    def test_checklist_includes_per_flag_callouts(self) -> None:
        accumulated = {
            "BATNA FLAGS:": ["hand-waved alt"],
            "COST FLAGS:": ["below floor"],
            "RELATIONSHIP FLAGS:": ["unacknowledged cost"],
        }
        items = SupplierBriefWorkflow._build_approver_checklist(
            make_request(), accumulated
        )
        flag_items = "\n".join(items)
        assert "BATNA FLAGS DETECTED" in flag_items
        assert "COST FLAGS DETECTED" in flag_items
        assert "RELATIONSHIP FLAGS DETECTED" in flag_items

    def test_checklist_baseline_items_always_present(self) -> None:
        empty = {h: [] for h in ("BATNA FLAGS:", "COST FLAGS:", "RELATIONSHIP FLAGS:")}
        items = SupplierBriefWorkflow._build_approver_checklist(make_request(), empty)
        text = "\n".join(items)
        assert "Category buyer review" in text
        assert "Finance sign-off" in text
        assert "Legal review" in text
