"""Unit tests for MakeVsBuyWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.industrial.workflows.make_vs_buy import (
    MakeVsBuyRequest,
    MakeVsBuyWorkflow,
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


def make_request(**kwargs: Any) -> MakeVsBuyRequest:
    defaults: dict[str, Any] = dict(
        component_summary="Motor-controller PCBA P/N 8042-447; 24k units/yr; design-owned.",
        internal_cost_basis="Should-cost $65.60/unit; material $48.20 + labour $4.10 + OH $8.40.",
        external_bid_summary="Vietnam EMS DDP $52.80; Mexico EMS DDP $58.40; both normalised.",
        capability_evidence="In-house PPAP3 Cpk 1.67; Vietnam PPAP2 18mo track; Mexico PPAP3.",
        ip_risk_context="Firmware loaded via test-fixture image; magnet-array EAR 3A001.b.2.",
        strategic_constraints="3-yr term; 12mo exit notice; in-house capacity 32k/yr.",
    )
    defaults.update(kwargs)
    return MakeVsBuyRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path,
    executor: FakeExecutor, reviewer: FakeReviewer,
) -> MakeVsBuyWorkflow:
    return MakeVsBuyWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Component Summary
Motor-controller PCBA, 24k units/yr, design owned by OEM.

## Internal Should-Cost
$65.60/unit; material $48.20, labour $4.10, OH $8.40, capex $3.10, opp $0, quality $1.80.

## External Bid Normalisation
Vietnam EMS DDP $52.80 (year-1 -$12.80 delta); Mexico EMS DDP $58.40.

## Capability Position
In-house PPAP3 Cpk 1.67; Vietnam PPAP2 with 4 SCAR closed.

## IP and Strategic Risk
Firmware via test-fixture image (no source exposure); magnet-array EAR license required.

## Recommendation
Dual-source: 40% in-house China-2 / 60% Mexico Tier-1. 3-yr term; 12mo exit notice.

## Evidence Gaps
Vietnam SCAR systemic-cause closure evidence not provided.

## Claims
[Source: internal_cost_basis] Internal should-cost is $65.60 per unit.
[Source: external_bid_summary] Vietnam DDP delta is -$12.80 year-1.
[Source: ip_risk_context] Magnet-array sensor requires EAR ECCN 3A001.b.2 license.
"""

_CLEAN_CRITIQUE = """\
Recommendation is defensible.

Overall score: 8.4/10
Key issues:
- Verify EAR license addressee before contract award.

COST FLAGS: None detected
CAPABILITY FLAGS: None detected
IP-LEAK FLAGS: None detected
"""


class TestMakeVsBuyConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.4, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1

    @pytest.mark.asyncio
    async def test_does_not_converge_when_cost_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: cost basis incomplete\n"
            "COST FLAGS:\n- External bid omits tooling amortisation\n"
            "CAPABILITY FLAGS: None detected\n"
            "IP-LEAK FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("tooling" in f for f in result.metadata["cost_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_capability_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: capability hand-waving\n"
            "COST FLAGS: None detected\n"
            "CAPABILITY FLAGS:\n- Vietnam PPAP2 lacks fixture-validation evidence\n"
            "IP-LEAK FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("fixture" in f for f in result.metadata["capability_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_ip_leak_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: IP exposure unmitigated\n"
            "COST FLAGS: None detected\n"
            "CAPABILITY FLAGS: None detected\n"
            "IP-LEAK FLAGS:\n- Industrial park shared with competitor OEMs without isolation plan\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("competitor" in f for f in result.metadata["ip_leak_flags"])


class TestMakeVsBuyOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.4, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered_into_ledger(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.4, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestMakeVsBuyRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        for fragment in [
            "Component summary:", "Internal cost basis:", "External bid summary:",
            "Capability evidence:", "IP risk context:", "Strategic constraints:",
        ]:
            assert fragment in text
