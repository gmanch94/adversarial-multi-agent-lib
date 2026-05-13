"""Unit tests for LoyaltyOfferWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.retail.workflows.loyalty_offer import (
    LoyaltyOfferRequest,
    LoyaltyOfferWorkflow,
    _DISCLAIMER,
    _MAX_ATTRIBUTE_ENTRIES,
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


def make_request(**kwargs: Any) -> LoyaltyOfferRequest:
    defaults: dict[str, Any] = dict(
        customer_segment=(
            "High-engagement dairy buyers (purchased >= 4 dairy SKUs in last 60 days "
            "with loyalty card), est. 84,000 households"
        ),
        offer_proposal=(
            "-15% on private-label dairy SKUs, two-week window, max 5 redemptions "
            "per household, valid in-store and curbside pickup"
        ),
        historical_response=(
            "2025 Q3 similar offer: 22% redemption among targeted segment, 3% free-rider "
            "rate on baseline category, $0.18/unit incremental margin lift"
        ),
        margin_floor="$0.85/unit",
        allowed_attributes=[
            "purchase_history_60d",
            "loyalty_tier",
            "store_visits_90d",
            "category_basket_share",
        ],
        disallowed_attributes=[
            "zip_code",
            "language_preference",
            "first_name",
            "household_income_inferred",
            "device_model",
        ],
        competing_offers=(
            "Regional competitor running -10% on national-brand dairy through Wk3; "
            "no internal concurrent dairy promo"
        ),
        gaming_risk=(
            "Basket-splitting across 2 transactions to maximise 5-redemption cap; "
            "spouse-account creation for second 5-redemption tranche"
        ),
    )
    defaults.update(kwargs)
    return LoyaltyOfferRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> LoyaltyOfferWorkflow:
    return LoyaltyOfferWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Segment Definition
High-engagement dairy buyers: purchase_history_60d shows >= 4 dairy SKUs (derives from
allowed: purchase_history_60d); loyalty_tier in {silver, gold, platinum} (derives from
allowed: loyalty_tier); store_visits_90d >= 3 (derives from allowed: store_visits_90d).

## Offer Mechanics
-15% off private-label dairy SKUs, two-week window, max 5 redemptions/household,
in-store + curbside.

## Margin Math
Baseline margin $1.15/unit. -15% discount = $0.17 reduction → realistic $0.98/unit
after free-rider adjustment (3%) and cannibalization on national brand ($0.05 net loss
captured per substitution). Net $0.98 > floor $0.85.

## Gaming Paths Considered
- Basket-splitting: mitigated by per-household cap derived from loyalty_id, not txn_id.
- Multi-account: mitigated by address-based household-key dedup at redemption time.
- Threshold-bumping: N/A (no threshold).

## Success Metric + Kill Criteria
Success: margin-positive lift > $0.20/unit vs holdout. Kill: free-rider rate > 8% by Day 7.

## Evidence Gaps
Free-rider estimate is from a different category (general grocery, not dairy).

## Claims
[Source: historical_response] Prior similar offer had 22% redemption.
[Source: margin_floor] Floor is $0.85/unit.
[Source: allowed_attributes] Segment derives from four allowlisted attributes.
"""

_CLEAN_CRITIQUE = """\
Solid design.

Overall score: 8.5/10
Key issues:
- Free-rider estimate from adjacent category is acceptable but flagged for post-launch validation.

FAIRNESS FLAGS: None detected
MARGIN FLAGS: None detected
GAMING FLAGS: None detected
"""


class TestLoyaltyConvergence:
    @pytest.mark.asyncio
    async def test_converges_when_no_flags_and_score_above_threshold(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1

    @pytest.mark.asyncio
    async def test_does_not_converge_when_fairness_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 8.0/10\nKey issues: proxy concern\n"
            "FAIRNESS FLAGS:\n- Segment narrows on ZIP-derived income inference\n"
            "MARGIN FLAGS: None detected\nGAMING FLAGS: None detected"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("ZIP-derived" in f for f in result.metadata["fairness_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_margin_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "FAIRNESS FLAGS: None detected\n"
            "MARGIN FLAGS:\n- Realistic scenario nets $0.78/unit, below floor $0.85\n"
            "GAMING FLAGS: None detected\nOverall score: 7.0/10"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("below floor" in f for f in result.metadata["margin_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_gaming_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "FAIRNESS FLAGS: None detected\nMARGIN FLAGS: None detected\n"
            "GAMING FLAGS:\n- Gift-card laundering path has no mitigation\n"
            "Overall score: 7.5/10"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.5, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Gift-card" in f for f in result.metadata["gaming_flags"])


class TestLoyaltyOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_metadata_keys_present(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        for key in (
            "segment_name",
            "fairness_flags",
            "margin_flags",
            "gaming_flags",
            "approver_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata

    @pytest.mark.asyncio
    async def test_claims_registered(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestExtractFlags:
    def test_extracts_fairness_flags_stops_at_margin_header(self) -> None:
        critique = (
            "FAIRNESS FLAGS:\n- ZIP proxy detected\n- Language preference proxy\n"
            "MARGIN FLAGS: None detected"
        )
        flags = LoyaltyOfferWorkflow._extract_flags(critique, "FAIRNESS FLAGS:")
        assert len(flags) == 2
        assert any("ZIP" in f for f in flags)

    def test_extracts_margin_flags_stops_at_gaming_header(self) -> None:
        critique = (
            "MARGIN FLAGS:\n- Adverse scenario fails floor\n"
            "GAMING FLAGS: None detected"
        )
        flags = LoyaltyOfferWorkflow._extract_flags(critique, "MARGIN FLAGS:")
        assert len(flags) == 1

    def test_returns_empty_when_none_detected_inline(self) -> None:
        flags = LoyaltyOfferWorkflow._extract_flags(
            "FAIRNESS FLAGS: None detected\nMARGIN FLAGS: ...", "FAIRNESS FLAGS:"
        )
        assert flags == []

    def test_returns_empty_when_header_absent(self) -> None:
        assert LoyaltyOfferWorkflow._extract_flags("clean.", "GAMING FLAGS:") == []


class TestLoyaltyRequestPromptText:
    def test_renders_all_labels(self) -> None:
        text = make_request().to_prompt_text()
        for label in [
            "Customer segment:",
            "Offer proposal:",
            "Historical response:",
            "Margin floor:",
            "Allowed attributes:",
            "Disallowed attributes",
            "Competing offers:",
            "Known gaming risks:",
        ]:
            assert label in text

    def test_attribute_list_truncates_past_cap(self) -> None:
        oversize = [f"attr_{i}" for i in range(_MAX_ATTRIBUTE_ENTRIES + 10)]
        req = make_request(allowed_attributes=oversize)
        text = req.to_prompt_text()
        assert "truncated" in text
        assert "attr_0" in text
        # Past-cap items not present
        assert f"attr_{_MAX_ATTRIBUTE_ENTRIES + 5}" not in text

    def test_empty_attribute_list_renders_placeholder(self) -> None:
        req = make_request(allowed_attributes=[])
        text = req.to_prompt_text()
        assert "(none specified)" in text


class TestBuildApproverChecklist:
    def test_checklist_includes_flag_callouts(self) -> None:
        accumulated = {
            "FAIRNESS FLAGS:": ["ZIP proxy"],
            "MARGIN FLAGS:": ["floor failed"],
            "GAMING FLAGS:": ["gift-card laundering"],
        }
        items = LoyaltyOfferWorkflow._build_approver_checklist(
            make_request(), accumulated
        )
        flag_items = "\n".join(items)
        assert "FAIRNESS FLAGS DETECTED" in flag_items
        assert "MARGIN FLAGS DETECTED" in flag_items
        assert "GAMING FLAGS DETECTED" in flag_items

    def test_checklist_skips_flag_callouts_when_clean(self) -> None:
        accumulated = {h: [] for h in ("FAIRNESS FLAGS:", "MARGIN FLAGS:", "GAMING FLAGS:")}
        items = LoyaltyOfferWorkflow._build_approver_checklist(
            make_request(), accumulated
        )
        text = "\n".join(items)
        assert "FAIRNESS FLAGS DETECTED" not in text
        assert "Legal review" in text  # baseline items always present
