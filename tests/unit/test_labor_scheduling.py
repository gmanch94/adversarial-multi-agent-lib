"""Unit tests for LaborSchedulingWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.retail.workflows.labor_scheduling import (
    LaborSchedulingWorkflow,
    SchedulingRequest,
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


def make_request(**kwargs: Any) -> SchedulingRequest:
    defaults: dict[str, Any] = dict(
        store_id="KRO-OH-0042",
        week_start="2026-05-18",
        projected_traffic="Mon:1200 Tue:1100 Wed:1150 Thu:1300 Fri:1800 Sat:2400 Sun:1600; peaks: Fri 5-7pm, Sat 11am-2pm",
        staff_roster=(
            "Alice (cashier, FT, avail all week); Bob (cashier, PT, unavail Fri); "
            "Carol (produce, FT, avail all week); Dave (stocker, PT, avail Mon-Thu); "
            "Eve (manager, FT, avail all week)"
        ),
        labor_budget="$4,200 for the week",
        local_events="High school graduation Sat morning; no other events",
        state_labor_law_notes=(
            "Ohio: 18+ no minor restrictions; OT >40h/week at 1.5x; "
            "30-min unpaid break required for shifts >6h"
        ),
        unemployment_rate="Local rate 4.2%; moderate labor pool; turnover risk low this quarter",
    )
    defaults.update(kwargs)
    return SchedulingRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> LaborSchedulingWorkflow:
    return LaborSchedulingWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Schedule
Mon: Eve 8-5 (mgr), Alice 9-6 (cash), Carol 7-4 (prod), Dave 6-2 (stock)
Tue: Eve 8-5, Alice 9-6, Carol 7-4, Dave 6-2
Wed: Eve 8-5, Alice 9-6, Carol 7-4, Dave 6-2
Thu: Eve 8-5, Alice 9-6, Carol 7-4, Dave 6-2
Fri: Eve 8-5, Alice 11-8 (peak coverage), Carol 7-4
Sat: Eve 7-4, Alice 9-6, Carol 7-4 (grad event)
Sun: Eve 10-6, Alice 10-6, Carol 9-5

## Coverage Analysis
Peak Fri 5-7pm: Alice + Eve on floor. Sat 11am-2pm: all three available.

## Labor Cost Estimate
Total hours: ~152. Estimated cost: $3,840 at avg $25.26/hr. Under $4,200 budget.

## Compliance Notes
All shifts ≤10h. Bob unavailability respected. No OT (Alice 38h, Eve 40h). All >6h shifts include break.

## Fairness Notes
FT staff (Alice, Eve, Carol) carry proportionate load. Dave (PT) at 32h — within availability.

## Evidence Gaps
No historical labor-to-sales ratio provided; coverage recommendations are estimated.

## Claims
[Source: staff_roster] Bob unavailable Friday — no Friday shift assigned.
[Source: state_labor_law_notes] OT threshold: >40h/week. Eve scheduled exactly 40h.
"""


class TestLaborConvergence:
    @pytest.mark.asyncio
    async def test_converges_when_score_meets_threshold_and_no_flags(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="COMPLIANCE FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert result.final_score == 8.0

    @pytest.mark.asyncio
    async def test_does_not_converge_when_compliance_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    8.0,
                    approved=True,
                    critique="COMPLIANCE FLAGS:\n- Alice scheduled 42h; exceeds 40h OT threshold",
                ),
                make_result(8.0, approved=True, critique="COMPLIANCE FLAGS: None detected"),
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
                make_result(6.0, approved=False, critique="Coverage gaps on Saturday."),
                make_result(6.5, approved=False, critique="Still understaffed at peak."),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 2


class TestLaborOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="COMPLIANCE FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_metadata_keys_present(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="COMPLIANCE FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "store_id" in result.metadata
        assert "week_start" in result.metadata
        assert "compliance_flags" in result.metadata
        assert "manager_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata

    @pytest.mark.asyncio
    async def test_compliance_flags_empty_when_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="COMPLIANCE FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["compliance_flags"] == []

    @pytest.mark.asyncio
    async def test_compliance_flags_accumulated(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    7.0,
                    approved=False,
                    critique="COMPLIANCE FLAGS:\n- Missing break for 8h shift",
                ),
                make_result(8.5, approved=True, critique="COMPLIANCE FLAGS: None detected"),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert any("break" in f.lower() for f in result.metadata["compliance_flags"])


class TestExtractComplianceFlags:
    def test_extracts_flags(self) -> None:
        critique = "Good coverage.\n\nCOMPLIANCE FLAGS:\n- Alice at 42h exceeds OT threshold\n- No break noted for 8h shift\n\nOverall score: 6/10"
        flags = LaborSchedulingWorkflow._extract_compliance_flags(critique)
        assert len(flags) == 2
        assert "Alice at 42h exceeds OT threshold" in flags

    def test_returns_empty_when_none_detected(self) -> None:
        critique = "COMPLIANCE FLAGS: None detected\nOverall score: 9/10"
        flags = LaborSchedulingWorkflow._extract_compliance_flags(critique)
        assert flags == []

    def test_returns_empty_when_section_absent(self) -> None:
        flags = LaborSchedulingWorkflow._extract_compliance_flags("Looks good.")
        assert flags == []


class TestSchedulingRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        assert "Store: KRO-OH-0042" in text
        assert "Week starting: 2026-05-18" in text
        assert "Projected traffic" in text
        assert "Staff roster" in text
        assert "Labor budget" in text
        assert "Local events" in text
        assert "Labor law" in text
        assert "Unemployment rate" in text
