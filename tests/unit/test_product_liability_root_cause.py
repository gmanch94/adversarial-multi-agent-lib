"""Unit tests for ProductLiabilityRootCauseWorkflow — no live API calls.

Veto + triple-flag (D-IND-1). Mirrors test_claims_reserve.py shape:
- convergence on clean input
- non-convergence per flag class (DESIGN-DEFECT / OPERATOR-ERROR / WARNING-ADEQUACY)
- veto halts with high score
- veto records flags from vetoed round
- no veto when directive is None
- output disclaimer present
- _extract_veto same-line + continuation + sibling-header behaviour
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.industrial.workflows.product_liability_root_cause import (
    ProductLiabilityRootCauseRequest,
    ProductLiabilityRootCauseWorkflow,
    _DISCLAIMER,
    _VETO_BANNER,
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


def make_request(**kwargs: Any) -> ProductLiabilityRootCauseRequest:
    defaults: dict[str, Any] = dict(
        incident_summary="2026-02-22 TR3600 pedestrian-strike Memphis TN; bilateral lower-leg fx.",
        telematics_and_trace="Speed 8.4 km/h in 4 km/h zone; geofence active; speed-limiter NOT engaged.",
        equipment_configuration="TR3600 + geofence module 8044-201 FW-1.8 (post ECO-25-0088).",
        standards_context="ANSI/ITSDF B56.1-2020; OSHA 1910.178; ITSDF B56.11.6 zone control.",
        operator_and_training="4-yr tenure; certificate current; did not sound horn at intersection.",
        field_failure_population="14 in-zone non-engagement incidents post-FW-1.8 vs 2 on prior FW-1.7.",
        initial_attribution="Operator-error: failure to sound horn, failure to slow at aisle intersection.",
    )
    defaults.update(kwargs)
    return ProductLiabilityRootCauseRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path, executor: FakeExecutor, reviewer: FakeReviewer,
) -> ProductLiabilityRootCauseWorkflow:
    return ProductLiabilityRootCauseWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Incident Summary
TR3600 pedestrian-strike; bilateral lower-leg fracture; chain-of-custody documented.

## Telematics and Trace Evidence
Speed 8.4 km/h in 4 km/h geofence zone. Geofence-state ACTIVE. Speed-limiter NOT engaged (interlock failure).

## Standards Comparison
ANSI B56.1 zone-control interlock per B56.11.6: as-built configuration nominally conformant; field behaviour non-conformant.

## Foreseeable-Misuse Analysis
Operator failure to sound horn is foreseeable misuse; design should tolerate via engineering controls.

## Design-Defect Hypothesis
FW-1.8 race condition in geofence-state-handler: 14 non-engagement incidents post-release. Design-defect probable.

## Operator-Error Attribution (if any)
Operator did not slow or sound horn; documented. But telematics show speed-limiter SHOULD have engaged regardless — design failure precedes operator action.

## Warning / Training Adequacy
Training-of-record adequate per OSHA 1910.178; placard conspicuous. Warning adequacy not contributory.

## Attribution and Next Actions
Mixed: design-defect (FW-1.8 race condition) primary; operator-error secondary. Trigger RecallScopeManufacturingWorkflow and pc.ClaimsReserveWorkflow.

## Claims
[Source: telematics_and_trace] Speed-limiter did not engage despite geofence zone active.
[Source: field_failure_population] FW-1.8 shows 14 in-zone non-engagement events in 12 months.
[Source: standards_context] B56.11.6 governs zone-control interlock behaviour.
"""

_CLEAN_CRITIQUE = """\
Attribution properly assigns design-defect contribution.

Overall score: 8.4/10
Key issues:
- Confirm CPSC 5-business-day clock from awareness date.

DESIGN-DEFECT FLAGS: None detected
OPERATOR-ERROR FLAGS: None detected
WARNING-ADEQUACY FLAGS: None detected
REVIEWER VETO: None
"""


class TestProdLiabConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.4, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    @pytest.mark.asyncio
    async def test_does_not_converge_when_design_defect_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: design analysis weak\n"
            "DESIGN-DEFECT FLAGS:\n- Foreseeable-misuse tolerance not analysed\n"
            "OPERATOR-ERROR FLAGS: None detected\nWARNING-ADEQUACY FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Foreseeable" in f for f in result.metadata["design_defect_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_operator_error_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: operator-error unsupported\n"
            "DESIGN-DEFECT FLAGS: None detected\n"
            "OPERATOR-ERROR FLAGS:\n- Telematics shows interlock should have engaged\n"
            "WARNING-ADEQUACY FLAGS: None detected\nREVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("interlock" in f for f in result.metadata["operator_error_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_warning_adequacy_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: warning conspicuity unclear\n"
            "DESIGN-DEFECT FLAGS: None detected\nOPERATOR-ERROR FLAGS: None detected\n"
            "WARNING-ADEQUACY FLAGS:\n- Placard legibility not verified at operator position\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Placard" in f for f in result.metadata["warning_adequacy_flags"])


class TestProdLiabVeto:
    @pytest.mark.asyncio
    async def test_veto_halts_immediately_with_high_score(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\nKey issues: structural\n"
            "DESIGN-DEFECT FLAGS: None detected\nOPERATOR-ERROR FLAGS: None detected\n"
            "WARNING-ADEQUACY FLAGS: None detected\n"
            "REVIEWER VETO: Catastrophic injury with FW-1.8 population pattern of "
            "14 non-engagement events — design-defect attribution required; do not "
            "file an operator-error defence position."
        )
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(9.0, approved=True, critique=veto_critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert "veto_reason" in result.metadata
        assert "design-defect" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert _VETO_BANNER in result.output

    @pytest.mark.asyncio
    async def test_veto_records_flags_from_vetoed_round(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.0/10\nKey issues: structural\n"
            "DESIGN-DEFECT FLAGS:\n- FW-1.8 pattern not analysed\n"
            "OPERATOR-ERROR FLAGS:\n- Telematics contradicts attribution\n"
            "WARNING-ADEQUACY FLAGS:\n- Placard legibility unverified\n"
            "REVIEWER VETO: Convenient operator-attribution masks design signal."
        )
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.0, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "veto_reason" in result.metadata
        assert result.metadata["design_defect_flags"] != []
        assert result.metadata["operator_error_flags"] != []
        assert result.metadata["warning_adequacy_flags"] != []

    @pytest.mark.asyncio
    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.4, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "veto_reason" not in result.metadata


class TestProdLiabOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.4, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output


class TestProdLiabExtractVeto:
    def test_returns_none_when_directive_is_none(self) -> None:
        assert ProductLiabilityRootCauseWorkflow._extract_veto("REVIEWER VETO: None", 1000) is None

    def test_returns_directive_on_same_line(self) -> None:
        v = ProductLiabilityRootCauseWorkflow._extract_veto(
            "REVIEWER VETO: escalate to safety committee, catastrophic", 1000
        )
        assert v is not None and "escalate" in v

    def test_returns_directive_on_continuation_lines(self) -> None:
        critique = "REVIEWER VETO:\nDesign-defect signal masked by operator-error attribution.\nEscalate immediately."
        v = ProductLiabilityRootCauseWorkflow._extract_veto(critique, 1000)
        assert v is not None and "Design-defect" in v and "Escalate" in v

    def test_sibling_header_stops_capture(self) -> None:
        # H-IND-1: hyphenated sibling headers (DESIGN-DEFECT FLAGS, etc.) now
        # also terminate the veto continuation parse.
        critique = (
            "REVIEWER VETO:\nReal directive line\n"
            "DESIGN-DEFECT FLAGS:\n- not part of veto"
        )
        v = ProductLiabilityRootCauseWorkflow._extract_veto(critique, 1000)
        assert v is not None and "Real directive" in v and "DESIGN-DEFECT" not in v


class TestProdLiabRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Incident summary:", "Telematics and trace:", "Equipment configuration:",
            "Standards context:", "Operator and training:", "Field failure population:",
            "Initial attribution:",
        ]:
            assert fragment in text
