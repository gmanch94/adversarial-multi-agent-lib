"""Unit tests for InventoryReplenishmentWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.retail.workflows.inventory_replenishment import (
    InventoryReplenishmentRequest,
    InventoryReplenishmentWorkflow,
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


def make_request(**kwargs: Any) -> InventoryReplenishmentRequest:
    defaults: dict[str, Any] = dict(
        dc_id="DC-DEN-014",
        sku_list=(
            "SKU-DAIRY-091: 9,800 on-hand, 1,800 on-order recv 2026-05-17. "
            "SKU-SHELF-330: 14,400 on-hand, no on-order."
        ),
        demand_forecast=(
            "DAIRY-091: 2,100/wk ±15%. SHELF-330: 1,250/wk ±10%. "
            "Source: DemandForecastWorkflow weeks 21–24."
        ),
        lead_times=(
            "FreshCo dairy: quoted 3d p90 4d ship Mon/Wed/Fri. "
            "Heartland shelf: quoted 7d p90 9d ship Tue/Thu."
        ),
        safety_stock_policy=(
            "Safety stock = max(1.5σ over lead time, 5d forward demand). "
            "Dairy is safety-stock-critical."
        ),
        dc_capacity=(
            "240 pallet positions/day, 3 doors, 06:00-14:00 Mon-Sat. "
            "Refrigerated capped 60/day."
        ),
        truck_economics=(
            "FTL break-even 22 pallets. FTL $1,400/leg, LTL $90/pallet."
        ),
        supplier_constraints=(
            "FreshCo MOQ 600 case pack 12 ship Mon/Wed/Fri. "
            "Heartland MOQ 1,200 case pack 24 ship Tue/Thu."
        ),
    )
    defaults.update(kwargs)
    return InventoryReplenishmentRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> InventoryReplenishmentWorkflow:
    return InventoryReplenishmentWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Forecast Consumption
DAIRY-091 central 2,100/wk, adverse 2,415/wk (+15%). SHELF-330 central
1,250/wk, adverse 1,375/wk (+10%).

## Per-SKU Schedule
DAIRY-091 | 9,800 OH | 1,800 OO (recv 05-17) | SS=2,250 | PO1 1,800 ship 05-18 recv 05-21 | PO2 1,800 ship 05-22 recv 05-25.
SHELF-330 | 14,400 OH | 0 OO | SS=1,560 | PO1 1,200 ship 05-19 recv 05-26.

## Stockout Projection
DAIRY-091 min on-hand week of 05-19: 3,300 cases (vs SS 2,250). Holds.
SHELF-330 min on-hand week of 06-02: 2,900 cases (vs SS 1,560). Holds.
Adverse case: DAIRY-091 holds at 2,475; SHELF-330 holds at 2,650.

## Capacity Check
Peak refrigerated receive 05-21: 30 pallets (DAIRY-091 PO1) — within 60 cap.
Ambient receive 05-26: 50 pallets — within 240 cap.
All MOQ + case-pack + ship-day adherence verified.

## Truck Economics
DAIRY-091 PO1: 30 pallets — FTL (cheaper).
SHELF-330 PO1: 50 pallets — FTL (cheaper).
No fragmentation opportunities.

## Success Metric + Kill Criteria
Metric: all SKUs hold SS at p50 + adverse. Kill: any projected breach
inside lead-time horizon.

## Evidence Gaps
Forecast variability stated as ±band; would prefer explicit σ.

## Claims
[Source: sku_list] DAIRY-091 starting on-hand 9,800 cases, 1,800 on-order.
[Source: lead_times] FreshCo p90 lead time is 4 days.
[Source: safety_stock_policy] Dairy is safety-stock-critical.
[Source: dc_capacity] Refrigerated receiving capped at 60 pallet positions/day.
"""

_CLEAN_CRITIQUE = """\
Solid schedule.

Overall score: 8.3/10
Key issues:
- Forecast σ not stated — would tighten the safety-stock computation.

LEAD-TIME FLAGS: None detected
STOCKOUT FLAGS: None detected
CAPACITY FLAGS: None detected
"""


class TestReplenishmentConvergence:
    @pytest.mark.asyncio
    async def test_converges_when_no_flags(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1

    @pytest.mark.asyncio
    async def test_does_not_converge_when_lead_time_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.8/10\nKey issues: lead-time gap\n"
            "LEAD-TIME FLAGS:\n- PO1 dated 05-18 with quoted 3d arrives 05-21, after projected stockout 05-20\n"
            "STOCKOUT FLAGS: None detected\nCAPACITY FLAGS: None detected"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.8, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("05-21" in f for f in result.metadata["lead_time_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_stockout_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "LEAD-TIME FLAGS: None detected\n"
            "STOCKOUT FLAGS:\n- DAIRY-091 adverse case breaches SS week of 05-26\n"
            "CAPACITY FLAGS: None detected\nOverall score: 7.0/10"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("adverse case" in f for f in result.metadata["stockout_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_capacity_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "LEAD-TIME FLAGS: None detected\nSTOCKOUT FLAGS: None detected\n"
            "CAPACITY FLAGS:\n- Peak refrigerated receive 05-21 = 78 pallets, exceeds 60 cap\n"
            "Overall score: 7.5/10"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.5, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("exceeds 60" in f for f in result.metadata["capacity_flags"])


class TestReplenishmentOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_metadata_keys_present(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        for key in (
            "dc_id",
            "lead_time_flags",
            "stockout_flags",
            "capacity_flags",
            "approver_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata

    @pytest.mark.asyncio
    async def test_claims_registered(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 4


class TestReplenishmentRequestPromptText:
    def test_renders_all_labels(self) -> None:
        text = make_request().to_prompt_text()
        for label in [
            "DC:",
            "SKU list",
            "Demand forecast:",
            "Lead times:",
            "Safety stock policy:",
            "DC capacity:",
            "Truck economics:",
            "Supplier constraints:",
        ]:
            assert label in text


class TestBuildApproverChecklist:
    def test_checklist_includes_per_flag_callouts(self) -> None:
        accumulated = {
            "LEAD-TIME FLAGS:": ["dated after stockout"],
            "STOCKOUT FLAGS:": ["adverse breach"],
            "CAPACITY FLAGS:": ["peak exceeds cap"],
        }
        items = InventoryReplenishmentWorkflow._build_approver_checklist(
            make_request(), accumulated
        )
        flag_items = "\n".join(items)
        assert "LEAD-TIME FLAGS DETECTED" in flag_items
        assert "STOCKOUT FLAGS DETECTED" in flag_items
        assert "CAPACITY FLAGS DETECTED" in flag_items

    def test_checklist_baseline_items_always_present(self) -> None:
        empty = {h: [] for h in ("LEAD-TIME FLAGS:", "STOCKOUT FLAGS:", "CAPACITY FLAGS:")}
        items = InventoryReplenishmentWorkflow._build_approver_checklist(
            make_request(), empty
        )
        text = "\n".join(items)
        assert "Supply-planning review" in text
        assert "DC ops sign-off" in text
        assert "Sourcing sign-off" in text
