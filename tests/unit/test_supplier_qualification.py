"""Unit tests for SupplierQualificationWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.industrial.workflows.supplier_qualification import (
    SupplierQualificationRequest,
    SupplierQualificationWorkflow,
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


def make_request(**kwargs: Any) -> SupplierQualificationRequest:
    defaults: dict[str, Any] = dict(
        supplier_summary="Idrotek SpA hydraulics; Reggio Emilia IT; $14.6M spend; re-qual.",
        financial_signals="EBITDA 8.1%; Paydex 67; RapidRatings FHR 38; OEM 22% of revenue.",
        quality_evidence="IATF 16949 current; PPAP3 clean; 38 DPPM escape vs target 80.",
        capacity_and_continuity="Single plant; BCP 2022 pre-COVID; capacity 24k for OEM.",
        sub_tier_and_geographic="Steel 60% IT cluster; magnet-array 100% single Shenzhen Tier-2.",
        proposed_qualification="Conditionally Qualified with three monitoring conditions.",
    )
    defaults.update(kwargs)
    return SupplierQualificationRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path, executor: FakeExecutor, reviewer: FakeReviewer,
) -> SupplierQualificationWorkflow:
    return SupplierQualificationWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Supplier Summary
Idrotek SpA; sole plant Reggio Emilia; re-qualification.

## Financial Position
EBITDA margin 8.1% (compressed); RapidRatings FHR 38; OEM 22% concentration.

## Quality System
IATF 16949 current; PPAP3 clean track; 38 DPPM (under target).

## Capacity and Continuity
Single-plant; BCP 2022 needs refresh; €40M property + €25M BI insurance.

## Sub-Tier and Geographic Posture
Steel Tier-2 60% Italy cluster; magnet-array single Tier-2 (Shenzhen) shared with two OEM Tier-1s.

## Recommendation
Conditionally Qualified: financial-stress monitoring; BCP refresh; magnet-array dual-source.

## Evidence Gaps
Italian banking covenant Q2 outcome not yet known.

## Claims
[Source: financial_signals] Supplier FHR is 38 in the Caution tier.
[Source: sub_tier_and_geographic] Magnet-array Tier-2 is shared with two OEM Tier-1s.
[Source: capacity_and_continuity] BCP/DRP was last revised in 2022 prior to recent disruptions.
"""

_CLEAN_CRITIQUE = """\
Re-qualification posture is defensible with conditions.

Overall score: 8.0/10
Key issues:
- Tighten BCP refresh deadline.

FINANCIAL FLAGS: None detected
QUALITY FLAGS: None detected
GEO-CONCENTRATION FLAGS: None detected
"""


class TestSupplierConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1

    @pytest.mark.asyncio
    async def test_does_not_converge_when_financial_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: financial stress\n"
            "FINANCIAL FLAGS:\n- FHR below 40 with no monitoring trigger\n"
            "QUALITY FLAGS: None detected\nGEO-CONCENTRATION FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("FHR" in f for f in result.metadata["financial_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_quality_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: quality evidence weak\n"
            "FINANCIAL FLAGS: None detected\n"
            "QUALITY FLAGS:\n- IATF surveillance findings closure evidence missing\n"
            "GEO-CONCENTRATION FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("IATF" in f for f in result.metadata["quality_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_geo_concentration_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: hidden single source\n"
            "FINANCIAL FLAGS: None detected\nQUALITY FLAGS: None detected\n"
            "GEO-CONCENTRATION FLAGS:\n- Magnet-array Tier-2 dual-source plan not on critical path\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Magnet-array" in f for f in result.metadata["geo_concentration_flags"])


class TestSupplierOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered_into_ledger(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestSupplierRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Supplier summary:", "Financial signals:", "Quality evidence:",
            "Capacity and continuity:", "Sub-tier and geographic:", "Proposed qualification:",
        ]:
            assert fragment in text
