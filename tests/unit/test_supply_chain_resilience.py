"""Unit tests for SupplyChainResilienceWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.industrial.workflows.supply_chain_resilience import (
    SupplyChainResilienceRequest,
    SupplyChainResilienceWorkflow,
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


def make_request(**kwargs: Any) -> SupplyChainResilienceRequest:
    defaults: dict[str, Any] = dict(
        commodity_summary="IGBT modules; $22.4M annual; critical; Tier-1 dual-source Infineon+Mitsubishi.",
        tier1_supplier_map="Infineon 60% DE+MY; Mitsubishi 40% JP+MY; active dual-source.",
        tier2_visibility="TSMC Hsinchu serves both Tier-1s — hidden single-source.",
        geographic_context="DE 35%, JP 25%, MY 20%, TW 15%, SG 5%; typhoon + seismic + Taiwan Strait.",
        lead_time_and_route_context="LT 16-18 weeks ±3; Malacca + Suez exposure; air 4-5x premium.",
        inventory_and_buffer="6-week strategic buffer; $2M air-freight authority; no critical-spare.",
        incident_or_trigger="Board contingency-planning review for Taiwan Strait scenario.",
    )
    defaults.update(kwargs)
    return SupplyChainResilienceRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path, executor: FakeExecutor, reviewer: FakeReviewer,
) -> SupplyChainResilienceWorkflow:
    return SupplyChainResilienceWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Commodity Summary
IGBT modules; $22.4M annual; critical commodity; Tier-1 dual-source.

## Single-Source Analysis
Tier-1 diverse but TSMC Hsinchu serves both Infineon (25%) and Mitsubishi (30%) — hidden single-source at Tier-2.

## Geographic Concentration
Country: DE 35%, JP 25%, MY 20%, TW 15% (concentrated at Hsinchu cluster). Political-risk: Taiwan Strait elevated.

## Lead-Time and Route Fragility
LT 16-18w ±3w; Malacca + Suez chokepoints; air-freight modal substitute at 4-5x.

## Inventory and Buffer Posture
6-week strategic buffer at OEM DCs; $2M air-freight authority.

## Resilience Action Plan
Action 1: TSMC qualify alternate fab (12-mo). Action 2: regional buffer to 10 weeks. Action 3: dual-source for substrate Tier-2.

## Evidence Gaps
Quantified probability for Taiwan Strait scenario not modelled.

## Claims
[Source: tier2_visibility] TSMC Hsinchu is a hidden single-source serving both Tier-1 suppliers.
[Source: lead_time_and_route_context] Lead-time variance is ±3 weeks on a 16-18 week baseline.
[Source: geographic_context] Taiwan exposure is 15% of commodity spend at the Tier-2 level.
"""

_CLEAN_CRITIQUE = """\
Resilience plan is defensible.

Overall score: 8.0/10
Key issues:
- Quantified scenario probability would strengthen the case.

SINGLE-SOURCE FLAGS: None detected
GEO-CONCENTRATION FLAGS: None detected
LEAD-TIME-FRAGILITY FLAGS: None detected
"""


class TestResilienceConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True

    @pytest.mark.asyncio
    async def test_does_not_converge_when_single_source_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: hidden Tier-2\n"
            "SINGLE-SOURCE FLAGS:\n- TSMC concentration not quantified at line level\n"
            "GEO-CONCENTRATION FLAGS: None detected\nLEAD-TIME-FRAGILITY FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("TSMC" in f for f in result.metadata["single_source_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_geo_concentration_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: cluster risk not addressed\n"
            "SINGLE-SOURCE FLAGS: None detected\n"
            "GEO-CONCENTRATION FLAGS:\n- Kulim/KL package-test cluster not in resilience plan\n"
            "LEAD-TIME-FRAGILITY FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Kulim" in f for f in result.metadata["geo_concentration_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_lead_time_fragility_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: route fragility\n"
            "SINGLE-SOURCE FLAGS: None detected\nGEO-CONCENTRATION FLAGS: None detected\n"
            "LEAD-TIME-FRAGILITY FLAGS:\n- Suez closure scenario buffer-day implication not stated\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Suez" in f for f in result.metadata["lead_time_fragility_flags"])


class TestResilienceOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestResilienceRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Commodity summary:", "Tier-1 supplier map:", "Tier-2 visibility:",
            "Geographic context:", "Lead-time and route context:",
            "Inventory and buffer:", "Incident or trigger:",
        ]:
            assert fragment in text
