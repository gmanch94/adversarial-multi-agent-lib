"""Unit tests for TelematicsAnomalyTriageWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.industrial.workflows.telematics_anomaly_triage import (
    TelematicsAnomalyTriageRequest,
    TelematicsAnomalyTriageWorkflow,
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


def make_request(**kwargs: Any) -> TelematicsAnomalyTriageRequest:
    defaults: dict[str, Any] = dict(
        asset_summary="TR2400 electric serial TR2400-2024-08812; ColdLink Dallas TX; 18 mo age.",
        signal_payload="Cell-7 thermal 51.4°C sustained 15min; +12°C above P95 baseline; +4.2σ.",
        duty_cycle_baseline="Heavy-duty 14hr/day; P95 thermal 39.4°C; FW-3.2 active.",
        recent_service_history="1000hr svc 2026-04-12 clean; BMS FW updated 2025-11-04.",
        customer_contract_context="4hr alarm / 24hr warning SLA; 3 spare trucks on-site.",
        parts_and_service_network="BMS board $420 (Dallas 4 in stock); cell module $1180 (Houston 24hr).",
        initial_recommendation="Dispatch within 24hr SLA; bring BMS board + 1 cell-module spare.",
    )
    defaults.update(kwargs)
    return TelematicsAnomalyTriageRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path, executor: FakeExecutor, reviewer: FakeReviewer,
) -> TelematicsAnomalyTriageWorkflow:
    return TelematicsAnomalyTriageWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Signal Summary
Cell-7 thermal sustained 51.4°C for 15 min; +12°C above P95 baseline; +4.2σ; detector confidence 0.83.

## Equipment and Customer Context
TR2400 in refrigerated-warehouse duty cycle; SLA 24-hr warning response.

## Failure-Mode Hypothesis
Top: cell-7 internal-short progression (consistent with 18% IR increase); next: BMS sensor drift.

## False-Positive Analysis
Base rate ~12% for sustained-thermal-only signals; cost-of-action $1800; cost-of-inaction (thermal runaway risk) catastrophic.

## Recommended Action
Dispatch — Standard (24-hr SLA); bring BMS cell-monitoring board + 1 cell module; verify cell-7 IR and pack voltage.

## Threshold for Escalation
Upgrade to Critical if any other cell crosses warn-tier OR alarm-tier (55 °C) reached.

## Evidence Gaps
Full pack IV-curve not yet pulled.

## Claims
[Source: signal_payload] Cell-7 temperature is 12 °C above the asset's P95 baseline.
[Source: parts_and_service_network] BMS replacement board is in Dallas DC stock.
[Source: customer_contract_context] Customer SLA allows 24-hour response on warning-tier signals.
"""

_CLEAN_CRITIQUE = """\
Triage well-anchored.

Overall score: 8.2/10
Key issues:
- Pull pack IV-curve before dispatch.

SIGNAL-EVIDENCE FLAGS: None detected
FALSE-POSITIVE-COST FLAGS: None detected
ACTIONABILITY FLAGS: None detected
"""


class TestTelematicsConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.2, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True

    @pytest.mark.asyncio
    async def test_does_not_converge_when_signal_evidence_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: signal weak\n"
            "SIGNAL-EVIDENCE FLAGS:\n- Single 15-min reading without repeat\n"
            "FALSE-POSITIVE-COST FLAGS: None detected\nACTIONABILITY FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("repeat" in f for f in result.metadata["signal_evidence_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_false_positive_cost_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: FP discipline missing\n"
            "SIGNAL-EVIDENCE FLAGS: None detected\n"
            "FALSE-POSITIVE-COST FLAGS:\n- Base rate not stated for this signal class\n"
            "ACTIONABILITY FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Base rate" in f for f in result.metadata["false_positive_cost_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_actionability_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: vague action\n"
            "SIGNAL-EVIDENCE FLAGS: None detected\nFALSE-POSITIVE-COST FLAGS: None detected\n"
            "ACTIONABILITY FLAGS:\n- Escalation threshold not specified\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Escalation" in f for f in result.metadata["actionability_flags"])


class TestTelematicsOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.2, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.2, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestTelematicsRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Asset summary:", "Signal payload:", "Duty-cycle baseline:",
            "Recent service history:", "Customer contract context:",
            "Parts and service network:", "Initial recommendation:",
        ]:
            assert fragment in text
