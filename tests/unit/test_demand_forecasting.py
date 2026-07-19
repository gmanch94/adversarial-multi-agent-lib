"""Unit tests for DemandForecastWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core._internal import extract_flags
from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.retail.workflows.demand_forecasting import (
    DemandForecastWorkflow,
    ForecastRequest,
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


def make_request(**kwargs: Any) -> ForecastRequest:
    defaults: dict[str, Any] = dict(
        store_id="KRO-OH-0042",
        sku="SKU-00123",
        product_category="dairy",
        historical_sales="Wk1:320 Wk2:310 Wk3:335 Wk4:340 Wk5:315 Wk6:328 Wk7:342 Wk8:330",
        current_inventory="on-hand: 180 units; in-transit: 200 units",
        lead_time_days="3",
        upcoming_events="Memorial Day weekend (Wk3); store loyalty promo -10% (Wk2)",
        seasonality_notes="Dairy demand rises ~8% May–Aug due to summer baking",
        weather_forecast="Warm and dry next 2 weeks; no precipitation expected",
        unemployment_rate="Local rate 4.2%, down 0.3pp YoY; consumer confidence stable",
    )
    defaults.update(kwargs)
    return ForecastRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> DemandForecastWorkflow:
    return DemandForecastWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Demand Signal Analysis
Baseline of ~330 units/week from 8-week history. Low variance (CV ~3%).

## Forecast
Wk1: 336 | Wk2: 302 (promo lift partially offset by -10% price) | Wk3: 370 (Memorial Day) | Wk4: 340

## Replenishment Recommendation
Order 480 units from supplier by Tuesday. Target delivery Thursday (3-day lead time).

## Key Assumptions
- Memorial Day lifts dairy ~15% based on historical holiday patterns.
- Promo reduces basket size but increases transactions; net -5% on unit volume.
- Weather has negligible impact on dairy demand.

## Evidence Gaps
No actuarial demand model baseline. Promotion uplift estimate is qualitative.

## Claims
[Source: historical_sales] Average weekly sales over 8 weeks: 327.5 units.
[Source: upcoming_events] Memorial Day weekend falls in forecast Wk3.
"""


class TestDemandConvergence:
    @pytest.mark.asyncio
    async def test_converges_when_score_meets_threshold_and_no_flags(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="ASSUMPTION FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert result.final_score == 8.0

    @pytest.mark.asyncio
    async def test_does_not_converge_when_assumption_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    8.0,
                    approved=True,
                    critique="ASSUMPTION FLAGS:\n- Memorial Day lift of 15% is unsubstantiated",
                ),
                make_result(8.0, approved=True, critique="ASSUMPTION FLAGS: None detected"),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2

    @pytest.mark.asyncio
    async def test_does_not_converge_when_score_below_threshold(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(6.0, approved=False, critique="Forecast not grounded."),
                make_result(6.5, approved=False, critique="Still weak."),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 2


class TestDemandOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="ASSUMPTION FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_metadata_keys_present(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="ASSUMPTION FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "store_id" in result.metadata
        assert "sku" in result.metadata
        assert "assumption_flags" in result.metadata
        assert "buyer_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata

    @pytest.mark.asyncio
    async def test_assumption_flags_empty_when_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="ASSUMPTION FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["assumption_flags"] == []

    @pytest.mark.asyncio
    async def test_assumption_flags_accumulated(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    7.0,
                    approved=False,
                    critique="ASSUMPTION FLAGS:\n- Holiday lift unsubstantiated",
                ),
                make_result(8.5, approved=True, critique="ASSUMPTION FLAGS: None detected"),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["assumption_flags"] == ["Holiday lift unsubstantiated"]


class TestExtractAssumptionFlags:
    """Flag extraction delegates to the shared ``extract_flags`` helper (F1
    migration off the private parser). Assertions are exact so a slurp or
    wiring regression fails instead of passing on membership."""

    def test_extracts_flags(self) -> None:
        critique = "Good.\n\nASSUMPTION FLAGS:\n- Holiday lift unsubstantiated\n- Weather factor unexplained\n\nOverall score: 6/10"
        flags = extract_flags(critique, "ASSUMPTION FLAGS:")
        assert flags == ["Holiday lift unsubstantiated", "Weather factor unexplained"]

    def test_stops_at_sibling_header(self) -> None:
        # Inherited H-IND-1 protection the private parser lacked: a sibling
        # uppercase header terminates the section instead of being slurped.
        critique = "ASSUMPTION FLAGS:\n- promo lift unsupported\nEVIDENCE FLAGS:\n- no source"
        assert extract_flags(critique, "ASSUMPTION FLAGS:") == ["promo lift unsupported"]

    def test_returns_empty_when_none_detected(self) -> None:
        critique = "ASSUMPTION FLAGS: None detected\nOverall score: 8/10"
        assert extract_flags(critique, "ASSUMPTION FLAGS:") == []

    def test_returns_empty_when_section_absent(self) -> None:
        assert extract_flags("No issues.", "ASSUMPTION FLAGS:") == []


class TestForecastRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        assert "Store: KRO-OH-0042" in text
        assert "SKU: SKU-00123" in text
        assert "Category: dairy" in text
        assert "Historical sales" in text
        assert "Current inventory" in text
        assert "Lead time" in text
        assert "Upcoming events" in text
        assert "Seasonality" in text
        assert "Weather forecast" in text
        assert "Unemployment rate" in text
