"""Unit tests for ParametricCropWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.pc.workflows.parametric_crop import (
    ParametricCropRequest,
    ParametricCropWorkflow,
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


def make_request(**kwargs: Any) -> ParametricCropRequest:
    defaults: dict[str, Any] = dict(
        producer_summary="Lindgren Farms; Stafford County KS; 2,400 ac dryland HRW wheat.",
        crop_and_yield_history="HRW wheat APH 38 bu/ac 10-yr; 2 catastrophic-yield years drought/heat.",
        loss_history="2020 / 2022 drought-heat losses indemnified under MPCI; 2023 minor hail.",
        proposed_cover_type="Rainfall-Index Apr-Jun trigger <6.0 in at Stafford-1; payout $50-150/ac.",
        data_source="NOAA Stafford-1 (USC00147747); 16 mi from acreage centroid; 96% uptime.",
        climate_baseline="20-yr mean 8.4 in; trend -0.18 in/decade; last 5 yrs 6.8 in mean.",
        reinsurance_context="Parametric add-on OUTSIDE SRA; Bermudan retro 50% QS; $2.1M agg headroom.",
    )
    defaults.update(kwargs)
    return ParametricCropRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path,
    executor: FakeExecutor, reviewer: FakeReviewer,
) -> ParametricCropWorkflow:
    return ParametricCropWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Producer & Crop Summary
Lindgren Farms; Stafford County KS; HRW wheat; APH 38 bu/ac.

## Peril Identification
Dominant cause: drought + heat during heading/grain-fill. Hail minor secondary.

## Proposed Cover Structure
Rainfall-Index parametric add-on; trigger 6.0 in Apr-Jun at Stafford-1; payout linear $50-150/ac.

## Peril-Match Justification
Rainfall-index correlates with drought-heat loss pathway (R² ~0.62 on 20-yr back-test).

## Basis-Risk Quantification
Station-to-acreage distance up to 27 mi; gridded-product alternative considered; producer disclosure drafted.

## Climate Baseline & Back-Test
20-yr mean 8.4 in; loss-cost at 6.0 in trigger as-is 14% / de-trended 9%; trend creep +5pp.

## Reinsurance / SRA Placement
Outside SRA; commercial retro 50% QS; aggregate consumed $360k of $2.1M headroom.

## Producer Disclosure
Plain-language disclosure drafted: trigger mechanics, basis-risk magnitude, NO claims dispute on non-fire.

## Evidence Gaps
30-day in-season weather forecast not factored into pricing.

## Claims
[Source: climate_baseline] Linear drying trend at Stafford-1 is approximately 0.18 in per decade.
[Source: data_source] Maximum tract-to-station distance is 27 miles.
[Source: reinsurance_context] This bind would consume $360k of $2.1M available aggregate.
"""


_CLEAN_CRITIQUE = """\
Cover design is defensible.

Overall score: 8.0/10
Key issues:
- 30-day in-season forecast could improve mid-season pricing.

PERIL-MATCH FLAGS: None detected
BASIS FLAGS: None detected
ATTACHMENT FLAGS: None detected
"""


class TestCropConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True

    @pytest.mark.asyncio
    async def test_does_not_converge_when_peril_match_flags(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: trigger doesn't catch heat-only loss\n"
            "PERIL-MATCH FLAGS:\n- Rainfall-only trigger misses pure heat-stress years\n"
            "BASIS FLAGS: None detected\n"
            "ATTACHMENT FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("heat-stress" in f for f in result.metadata["peril_match_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_basis_flags(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: station too far\n"
            "PERIL-MATCH FLAGS: None detected\n"
            "BASIS FLAGS:\n- 27-mile max tract distance creates moderate-to-high spatial basis risk\n"
            "ATTACHMENT FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("spatial basis" in f for f in result.metadata["basis_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_attachment_flags(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: trend not addressed\n"
            "PERIL-MATCH FLAGS: None detected\n"
            "BASIS FLAGS: None detected\n"
            "ATTACHMENT FLAGS:\n- 6.0 in threshold is below as-is 30th-percentile under trend creep\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("trend creep" in f for f in result.metadata["attachment_flags"])


class TestCropOutputStructure:
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


class TestParametricCropRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        for fragment in [
            "Producer summary:",
            "Crop and yield history:",
            "Loss history:",
            "Proposed cover type:",
            "Data source:",
            "Climate baseline:",
            "Reinsurance context:",
        ]:
            assert fragment in text
