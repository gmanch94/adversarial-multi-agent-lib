"""Unit tests for EnvironmentalImpairmentWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.pc.workflows.environmental_impairment import (
    EnvironmentalImpairmentRequest,
    EnvironmentalImpairmentWorkflow,
    _DISCLAIMER,
    _VETO_BANNER,
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


def make_request(**kwargs: Any) -> EnvironmentalImpairmentRequest:
    defaults: dict[str, Any] = dict(
        site_summary="Former dry-cleaner / current office park; Allegheny County PA.",
        site_history="1968-2001 PCE dry-cleaning; 1996 PA DEP NOV + consent order. Phase I 2022 REC.",
        pollution_condition="PCE groundwater plume MW-3 1,200 ug/L; migrated to adjacent parcel; indoor-air exposure 2024.",
        policy_form="PLL claims-made; $5M aggregate; retro 2022-08-15; known-condition exclusion I.1.f.",
        governing_state="Pennsylvania; J.H. France continuous-trigger; Koppers pro-rata.",
        regulator_status="PA HSCA listed; NOT NPL; surface-water NRD trustees (PA Game/Fish).",
        co_insurer_history="Three prior carriers 2004-2021; pre-2002 carriers unknown.",
        proposed_decision_or_reserve="DENY under known-condition exclusion; reserve $4.2M if coverage attaches.",
    )
    defaults.update(kwargs)
    return EnvironmentalImpairmentRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path,
    executor: FakeExecutor, reviewer: FakeReviewer,
) -> EnvironmentalImpairmentWorkflow:
    return EnvironmentalImpairmentWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Site & Loss Summary
Former dry-cleaner; PCE plume migrated to adjacent parcel; third-party PD/BI claim.

## Site History & Known Conditions
1996 PA DEP consent order is REC under Phase I; pre-retro-date known condition.

## Coverage Trigger
PA recognises continuous-trigger (J.H. France); plume formation pre-2022 retro date.

## Policy-Period Attribution
Pro-rata allocation under Koppers; pre-2022 carriers carry majority of liability.

## Regulatory Overlap
PA HSCA inventory; NRD trustees Saw Mill Run (Game/Fish); no CERCLA federal PRP.

## Coverage Conclusion / Reserve Recommendation
DENY under known-condition I.1.f (REC identified pre-retro-date); ROR pending counsel.

## Next Actions
Policy archaeology pre-2002; PA HSCA voluntary cleanup framework; NRD trustee outreach.

## Evidence Gaps
Phase II groundwater modeling not yet on file; need plume extent map.

## Claims
[Source: site_history] 1996 PA DEP consent order is a recognized environmental condition.
[Source: governing_state] PA Sup. Ct. recognises continuous-trigger doctrine for long-tail.
[Source: policy_form] Retroactive date is 2022-08-15; pre-retro known conditions excluded.
"""


_CLEAN_CRITIQUE = """\
Analysis is defensible.

Overall score: 8.5/10
Key issues:
- Plume extent map should be obtained.

KNOWN-CONDITION FLAGS: None detected
TAIL FLAGS: None detected
REGULATORY-OVERLAP FLAGS: None detected
REVIEWER VETO: None
"""


class TestEnvironmentalConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    @pytest.mark.asyncio
    async def test_does_not_converge_when_known_condition_flags(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: REC not mapped\n"
            "KNOWN-CONDITION FLAGS:\n- Phase I REC not mapped to I.1.f clause\n"
            "TAIL FLAGS: None detected\n"
            "REGULATORY-OVERLAP FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("REC" in f for f in result.metadata["known_condition_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_tail_flags(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: trigger doctrine missing\n"
            "KNOWN-CONDITION FLAGS: None detected\n"
            "TAIL FLAGS:\n- Pre-2002 carrier identification not addressed\n"
            "REGULATORY-OVERLAP FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Pre-2002" in f for f in result.metadata["tail_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_regulatory_overlap_flags(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: NRD not addressed\n"
            "KNOWN-CONDITION FLAGS: None detected\n"
            "TAIL FLAGS: None detected\n"
            "REGULATORY-OVERLAP FLAGS:\n- Natural Resource Damages trustee notice missing\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Natural Resource" in f for f in result.metadata["regulatory_overlap_flags"])


class TestEnvironmentalVeto:
    @pytest.mark.asyncio
    async def test_veto_halts_immediately_with_high_score(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\nKey issues: structural\n"
            "KNOWN-CONDITION FLAGS: None detected\n"
            "TAIL FLAGS: None detected\n"
            "REGULATORY-OVERLAP FLAGS: None detected\n"
            "REVIEWER VETO: Reasonable interpretation of pollution event-trigger "
            "supports coverage under PA continuous-trigger; proposed denial creates "
            "bad-faith exposure — escalate to environmental counsel."
        )
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(9.0, approved=True, critique=veto_critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert "veto_reason" in result.metadata
        assert "continuous-trigger" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert _VETO_BANNER in result.output

    @pytest.mark.asyncio
    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "veto_reason" not in result.metadata


class TestEnvironmentalOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered_into_ledger(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestEnvironmentalRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        for fragment in [
            "Site summary:",
            "Site history:",
            "Pollution condition:",
            "Policy form:",
            "Governing state:",
            "Regulator status:",
            "Co-insurer history:",
            "Proposed decision / reserve:",
        ]:
            assert fragment in text
