"""Unit tests for PromoMarkdownWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.retail.workflows.promo_markdown import (
    PromoMarkdownWorkflow,
    PromoRequest,
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


def make_request(**kwargs: Any) -> PromoRequest:
    defaults: dict[str, Any] = dict(
        sku="SKU-44210-COLA12",
        category="beverages",
        current_price="$6.49 (12-pack 12oz cans)",
        inventory_on_hand="DC: 14,400 cases; stores combined: 3,200 cases",
        weeks_of_supply="4.2 weeks at current run rate",
        competitor_pricing="Competitor A: $5.99 (regular); $4.99 promo Wk2 only",
        elasticity_estimate=(
            "Category benchmark from 2025 Q4 price-test: -1.4 ± 0.3 for "
            "20–25% off depth on national-brand 12-pack carbonated soft drinks"
        ),
        margin_floor="$0.42/unit (12-pack contribution margin floor)",
        promo_window="2026-05-25 to 2026-06-01 (Memorial Day week)",
        cannibalization_risk=(
            "Private-label 12-pack cola (substitution rate ~25%); 8-pack 16oz "
            "bottles same brand (rate ~12%); sports-drink 12-pack (rate ~5%)"
        ),
    )
    defaults.update(kwargs)
    return PromoRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> PromoMarkdownWorkflow:
    return PromoMarkdownWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Elasticity Assumption
Use -1.4 from 2025 Q4 category benchmark (band ±0.3). Adverse case: -1.1.

## Promo Mechanic
20% off, in-store + curbside, 7-day window, no stacking with category coupons.

## Expected Lift
Central: +28% unit volume. Adverse: +22%.

## Margin Math
Central: discount $1.30 / unit; cannibalization $0.18; free-rider $0.20; net $0.55 > floor.
Adverse: discount $1.30; cannibalization $0.22; free-rider $0.28; net $0.45 > floor.

## Timing Risk
Memorial Day demand peak — inflates lift read; mitigated with paired holdout.

## Success Metric + Kill Criteria
Success: incremental margin > $50K. Kill: free-rider rate > 65% by Day 3.

## Evidence Gaps
No prior price-test on 12-pack at 20% off in this region.

## Claims
[Source: elasticity_estimate] Category elasticity -1.4 ± 0.3.
[Source: margin_floor] Floor is $0.42 per unit.
[Source: cannibalization_risk] Three adjacent SKUs identified.
"""

_CLEAN_CRITIQUE = """\
Solid plan.

Overall score: 8.2/10
Key issues:
- Region-level price-test would tighten elasticity claim.

ELASTICITY FLAGS: None detected
MARGIN FLAGS: None detected
TIMING FLAGS: None detected
"""


class TestPromoConvergence:
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
    async def test_does_not_converge_when_elasticity_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.8/10\nKey issues: extrapolation\n"
            "ELASTICITY FLAGS:\n- Working elasticity outside benchmark band\n"
            "MARGIN FLAGS: None detected\nTIMING FLAGS: None detected"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.8, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("outside benchmark" in f for f in result.metadata["elasticity_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_margin_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "ELASTICITY FLAGS: None detected\n"
            "MARGIN FLAGS:\n- Adverse case nets $0.38, below floor $0.42\n"
            "TIMING FLAGS: None detected\nOverall score: 7.0/10"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("below floor" in f for f in result.metadata["margin_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_timing_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "ELASTICITY FLAGS: None detected\nMARGIN FLAGS: None detected\n"
            "TIMING FLAGS:\n- Window overlaps with bread-aisle promo, no mitigation\n"
            "Overall score: 7.5/10"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.5, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("bread-aisle" in f for f in result.metadata["timing_flags"])


class TestPromoOutputStructure:
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
            "sku",
            "category",
            "elasticity_flags",
            "margin_flags",
            "timing_flags",
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
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestExtractFlags:
    def test_extracts_elasticity_flags_stops_at_margin_header(self) -> None:
        critique = (
            "ELASTICITY FLAGS:\n- Outside band\n- Borrowed category\n"
            "MARGIN FLAGS: None detected"
        )
        flags = PromoMarkdownWorkflow._extract_flags(critique, "ELASTICITY FLAGS:")
        assert len(flags) == 2

    def test_extracts_timing_flags(self) -> None:
        critique = (
            "TIMING FLAGS:\n- Memorial Day overlap inflates lift\nOverall score: 7/10"
        )
        flags = PromoMarkdownWorkflow._extract_flags(critique, "TIMING FLAGS:")
        assert len(flags) == 1

    def test_returns_empty_when_none_detected(self) -> None:
        assert (
            PromoMarkdownWorkflow._extract_flags("MARGIN FLAGS: None detected", "MARGIN FLAGS:")
            == []
        )

    def test_returns_empty_when_header_absent(self) -> None:
        assert PromoMarkdownWorkflow._extract_flags("clean.", "TIMING FLAGS:") == []


class TestPromoRequestPromptText:
    def test_renders_all_labels(self) -> None:
        text = make_request().to_prompt_text()
        for label in [
            "SKU:",
            "Category:",
            "Current price:",
            "Inventory on hand:",
            "Weeks of supply:",
            "Competitor pricing:",
            "Elasticity estimate:",
            "Margin floor:",
            "Promo window:",
            "Cannibalization risk:",
        ]:
            assert label in text


class TestBuildApproverChecklist:
    def test_checklist_includes_per_flag_callouts(self) -> None:
        accumulated = {
            "ELASTICITY FLAGS:": ["outside band"],
            "MARGIN FLAGS:": ["floor breached"],
            "TIMING FLAGS:": ["overlap"],
        }
        items = PromoMarkdownWorkflow._build_approver_checklist(
            make_request(), accumulated
        )
        flag_items = "\n".join(items)
        assert "ELASTICITY FLAGS DETECTED" in flag_items
        assert "MARGIN FLAGS DETECTED" in flag_items
        assert "TIMING FLAGS DETECTED" in flag_items

    def test_checklist_baseline_items_always_present(self) -> None:
        empty = {h: [] for h in ("ELASTICITY FLAGS:", "MARGIN FLAGS:", "TIMING FLAGS:")}
        items = PromoMarkdownWorkflow._build_approver_checklist(make_request(), empty)
        text = "\n".join(items)
        assert "Category-manager review" in text
        assert "Finance sign-off" in text
