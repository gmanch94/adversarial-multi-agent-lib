"""Unit tests for EngineeringChangeOrderWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.industrial.workflows.engineering_change_order import (
    EngineeringChangeOrderRequest,
    EngineeringChangeOrderWorkflow,
    _DISCLAIMER,
)
from .fakes import FakeExecutor, FakeReviewer


def make_config(tmp_path: Path, **kwargs: Any) -> Config:
    defaults: dict[str, Any] = dict(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path), max_review_rounds=3, score_threshold=7.5,
    )
    defaults.update(kwargs)
    return Config(**defaults)


def make_result(score: float, *, approved: bool, critique: str = "") -> ReviewResult:
    return ReviewResult(score=score, critique=critique, suggestions=[], approved=approved)


def make_request(**kwargs: Any) -> EngineeringChangeOrderRequest:
    defaults: dict[str, Any] = dict(
        change_summary="ECO-26-0114 IGBT module supersession on PCBA 8042-447 Rev D→E.",
        affected_part_numbers="8042-447 Rev D→E; 8042-447-IGBT Infineon→Mitsubishi; svc P/N 8042-447S.",
        f3_analysis="Form ≤0.4mm; fit same mounting + thermal pad; function Vce-sat within 8%.",
        fmea_context="Over-temp: S6 O2 D4 RPN48; short-circuit latch-up: S9 O1 D3 RPN27.",
        deployed_product_context="42k PCBAs in field; FW-2.4/2.6/2.7 active; service 340/mo.",
        supplier_and_tooling_context="Infineon EOL Q1-2026; Mitsubishi PPAP3 approved; fixture FW update needed.",
    )
    defaults.update(kwargs)
    return EngineeringChangeOrderRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path, executor: FakeExecutor, reviewer: FakeReviewer,
) -> EngineeringChangeOrderWorkflow:
    return EngineeringChangeOrderWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Change Summary
IGBT module supersession Infineon → Mitsubishi on PCBA 8042-447; serial-effective ≥240000.

## Supersession Rules
Form / fit interchangeable. Function NOT bidirectional due to gate-drive +15/-9V vs +15/-8V; one-way replacement only. Service-parts catalog needs distinct P/N for legacy.

## FMEA Delta
Over-temp row: S6 O2 D4 → S6 O3 D4 (occurrence +1 due to thermal-pad footprint variance). Short-circuit row unchanged.

## Regression Risk
Bench DV/PV; system integration on TR2400 + TR3600; firmware compatibility matrix FW-2.4 / 2.6 / 2.7 × old/new PCBA tested; field trial 200 units 90 days.

## Supplier and Tooling Impact
PPAP3 first-article approved; fixture firmware update 4 weeks; new fault-coverage validation required.

## Service and Aftermarket
Service-bulletin SB-26-018; legacy P/N retained for pre-240000 service; on-failure retrofit recommendation.

## CAB Recommendation
Approve with conditions: condition 1 fixture update before run; condition 2 field-trial 200 units complete.

## Evidence Gaps
Mitsubishi long-term reliability data limited to 18 months.

## Claims
[Source: change_summary] The ECO supersedes IGBT module across PCBA 8042-447 Rev D to Rev E.
[Source: f3_analysis] Gate-drive voltage differs between modules (+15/-9V vs +15/-8V).
[Source: deployed_product_context] About 42,000 PCBAs are field-installed across firmware FW-2.4 / 2.6 / 2.7.
"""

_CLEAN_CRITIQUE = """\
ECO impact is well-bounded.

Overall score: 8.1/10
Key issues:
- Confirm Mitsubishi reliability data band before service-parts catalog commit.

SUPERSESSION FLAGS: None detected
FMEA-DELTA FLAGS: None detected
REGRESSION FLAGS: None detected
"""


class TestECOConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.1, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True

    @pytest.mark.asyncio
    async def test_does_not_converge_when_supersession_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: F/F/F weak\n"
            "SUPERSESSION FLAGS:\n- Function bidirectional claimed without gate-drive evidence\n"
            "FMEA-DELTA FLAGS: None detected\nREGRESSION FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Function" in f for f in result.metadata["supersession_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_fmea_delta_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: FMEA not refreshed\n"
            "SUPERSESSION FLAGS: None detected\n"
            "FMEA-DELTA FLAGS:\n- No PFMEA update for thermal-pad footprint change\n"
            "REGRESSION FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("thermal" in f for f in result.metadata["fmea_delta_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_regression_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: regression coverage gap\n"
            "SUPERSESSION FLAGS: None detected\nFMEA-DELTA FLAGS: None detected\n"
            "REGRESSION FLAGS:\n- FW-2.4 cross-compatibility not in regression matrix\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("FW-2.4" in f for f in result.metadata["regression_flags"])


class TestECOOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.1, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.1, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestECORequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Change summary:", "Affected part numbers:", "F/F/F analysis:",
            "FMEA context:", "Deployed product context:", "Supplier and tooling context:",
        ]:
            assert fragment in text
