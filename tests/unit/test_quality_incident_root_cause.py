"""Unit tests for QualityIncidentRootCauseWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.industrial.workflows.quality_incident_root_cause import (
    QualityIncidentRootCauseRequest,
    QualityIncidentRootCauseWorkflow,
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


def make_request(**kwargs: Any) -> QualityIncidentRootCauseRequest:
    defaults: dict[str, Any] = dict(
        incident_summary="2026-03-12 TR2400 seal extrusion 1840hr ops; oil pool; no injury.",
        evidence_inventory="Teardown: gland-edge extrusion; burr 0.06mm; SPC 8/30 over Ra spec.",
        initial_causal_hypothesis="Tool-life exceeded; AQL sampling missed out-of-spec parts.",
        containment_scope="WIP 840 sorted; finished 560 sorted; in-transit partial; field 14.2k not addressed.",
        process_and_design_context="PFMEA RPN 42 post-Q3-2024 (pre-change 14); SPC reaction-plan ineffective.",
        adjacent_products="TR2400 only on this line; same line serves scissor-lift customers.",
    )
    defaults.update(kwargs)
    return QualityIncidentRootCauseRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path, executor: FakeExecutor, reviewer: FakeReviewer,
) -> QualityIncidentRootCauseWorkflow:
    return QualityIncidentRootCauseWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Incident Summary
TR2400 cylinder seal extrusion at 1840 ops hrs; outer static seal at gland edge.

## Evidence Inventory
Gland burr 0.06mm vs 0.02 spec; SPC 8/30 over Ra; profilometer GR&R 22%.

## Causal Chain (5-Why or Equivalent)
Why1 oil loss → seal extrusion. Why2 → gland burr 0.06mm. Why3 → tool worn past 1150 cycles vs 800 spec. Why4 → tool-life monitoring downgraded. Why5 → in-process gauge moved from 100% to AQL Q3 2024 (root cause).

## Containment
WIP + finished sorted; in-transit + DC + field (14.2k) requires expanded sort plan with engineering screen.

## Systemic Read-Across
Scissor-lift customer parts machined on same line — read-across notice required.

## Corrective and Preventive Actions
CAPA-26-114: reinstate 100% in-process gauge; SPC running-average reaction plan; tool-life enforcement.

## Evidence Gaps
Field-fleet failure-mode population not yet queried.

## Claims
[Source: evidence_inventory] SPC shows 8 of 30 recent units exceeded the Ra spec.
[Source: process_and_design_context] PFMEA RPN moved from 14 to 42 after the Q3 2024 change.
[Source: adjacent_products] The same machining line serves scissor-lift customers.
"""

_CLEAN_CRITIQUE = """\
Root cause is well-anchored.

Overall score: 8.3/10
Key issues:
- Confirm scissor-lift customer read-across before closure.

CAUSAL-CHAIN FLAGS: None detected
CONTAINMENT FLAGS: None detected
SYSTEMIC FLAGS: None detected
"""


class TestQualityConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True

    @pytest.mark.asyncio
    async def test_does_not_converge_when_causal_chain_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: shallow chain\n"
            "CAUSAL-CHAIN FLAGS:\n- 5-Why stops at operator without proving operator-proof control\n"
            "CONTAINMENT FLAGS: None detected\nSYSTEMIC FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("operator-proof" in f for f in result.metadata["causal_chain_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_containment_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: containment narrow\n"
            "CAUSAL-CHAIN FLAGS: None detected\n"
            "CONTAINMENT FLAGS:\n- Field-deployed scope excluded with no sort method\n"
            "SYSTEMIC FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Field-deployed" in f for f in result.metadata["containment_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_systemic_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: read-across missing\n"
            "CAUSAL-CHAIN FLAGS: None detected\nCONTAINMENT FLAGS: None detected\n"
            "SYSTEMIC FLAGS:\n- Scissor-lift customer not notified despite shared line\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Scissor" in f for f in result.metadata["systemic_flags"])


class TestQualityOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestQualityRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Incident summary:", "Evidence inventory:", "Initial causal hypothesis:",
            "Containment scope:", "Process and design context:", "Adjacent products:",
        ]:
            assert fragment in text
