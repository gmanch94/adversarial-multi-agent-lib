"""Unit tests for RecallScopeManufacturingWorkflow — no live API calls.

Veto + triple-flag. Mirrors test_recall_scope.py (retail) shape.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.industrial.workflows.recall_scope_manufacturing import (
    RecallScopeManufacturingRequest,
    RecallScopeManufacturingWorkflow,
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


def make_request(**kwargs: Any) -> RecallScopeManufacturingRequest:
    defaults: dict[str, Any] = dict(
        trigger_summary="TR3600 FW-1.8 geofence speed-limiter non-engagement; pedestrian-strike injury; CPSC Tier 1+2.",
        evidence_inventory="14 in-zone non-engagement events on FW-1.8 vs 2 on FW-1.7; bench reproduction confirmed.",
        fleet_serial_traceability="6400 TR3600 + geofence + FW-1.8 units; 1840 EU + 320 CA + remainder US.",
        adjacent_product_exposure="TR2400 + TR4800 use different module 8044-403 — not affected.",
        regulatory_context="CPSC §15(b) 5-day clock from 2026-02-22; EU GPSR Article 5 + per-member; Canada CCPSA.",
        service_capacity_context="OTA-capable for 4800 units; 1600 require technician; capacity 2400/28-day.",
        proposed_scope="All 6400 global; mandatory FW-1.8→FW-1.9 update; CPSC report drafted; dealer cascade.",
    )
    defaults.update(kwargs)
    return RecallScopeManufacturingRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path, executor: FakeExecutor, reviewer: FakeReviewer,
) -> RecallScopeManufacturingWorkflow:
    return RecallScopeManufacturingWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Trigger and Hazard Summary
Geofence speed-limiter non-engagement on FW-1.8; injury occurred; CPSC §15(b) Tier 1 (serious injury) and Tier 2 (unreasonable risk).

## Evidence Inventory
14 events in 12 months on FW-1.8 vs 2 on FW-1.7; engineering bench-reproduction on 4 units.

## Fleet Scope
6,400 TR3600 + geofence + FW-1.8 globally: US 4,240 + EU 1,840 + Canada 320 + 12 pre-prod.

## Regulatory Notifications
CPSC §15(b) report 5-business-day clock from 2026-02-22; OSHA customer-side; EU GPSR Article 5 + DE/FR/IT/NL market surveillance; Canada CCPSA.

## Service Action Plan
Mandatory FW-1.8 → FW-1.9 update; 4,800 OTA-capable; 1,600 technician visits (28-day capacity).

## Reinsurance and Liability
Above product-liability retention; treaty notice drafted.

## Recall Decision
Initiate; product-safety committee + outside regulatory counsel approve.

## Evidence Gaps
EU per-member-state addressee list pending counsel confirmation.

## Claims
[Source: trigger_summary] CPSC Tier 1 substantial-product-hazard applies because serious injury occurred.
[Source: fleet_serial_traceability] 6,400 units are affected globally across three regions.
[Source: regulatory_context] CPSC 5-business-day clock began on 2026-02-22.
"""

_CLEAN_CRITIQUE = """\
Scope and notifications are complete.

Overall score: 8.5/10
Key issues:
- Confirm EU per-member-state addressee list.

TRIGGER-EVIDENCE FLAGS: None detected
FLEET-SCOPE FLAGS: None detected
REGULATORY-NOTIFY FLAGS: None detected
REVIEWER VETO: None
"""


class TestRecallConvergence:
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
    async def test_does_not_converge_when_trigger_evidence_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: evidence anecdotal\n"
            "TRIGGER-EVIDENCE FLAGS:\n- Field-failure population not quantified\n"
            "FLEET-SCOPE FLAGS: None detected\nREGULATORY-NOTIFY FLAGS: None detected\nREVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("population" in f for f in result.metadata["trigger_evidence_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_fleet_scope_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: scope narrow\n"
            "TRIGGER-EVIDENCE FLAGS: None detected\n"
            "FLEET-SCOPE FLAGS:\n- Pre-production / engineering builds excluded without basis\n"
            "REGULATORY-NOTIFY FLAGS: None detected\nREVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Pre-production" in f for f in result.metadata["fleet_scope_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_regulatory_notify_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: notification missing\n"
            "TRIGGER-EVIDENCE FLAGS: None detected\nFLEET-SCOPE FLAGS: None detected\n"
            "REGULATORY-NOTIFY FLAGS:\n- Canada CCPSA notification not on list\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("CCPSA" in f for f in result.metadata["regulatory_notify_flags"])


class TestRecallVeto:
    @pytest.mark.asyncio
    async def test_veto_halts_immediately_with_high_score(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.2/10\nKey issues: scope-vs-evidence mismatch\n"
            "TRIGGER-EVIDENCE FLAGS: None detected\nFLEET-SCOPE FLAGS: None detected\n"
            "REGULATORY-NOTIFY FLAGS: None detected\n"
            "REVIEWER VETO: Serious-injury occurred and population shows non-random "
            "pattern; current scope misses 12 pre-production units; CPSC 5-day clock "
            "already running. Escalate to product-safety committee + outside counsel."
        )
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(9.2, approved=True, critique=veto_critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert "veto_reason" in result.metadata
        assert "Serious-injury" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert _VETO_BANNER in result.output

    @pytest.mark.asyncio
    async def test_veto_records_flags_from_vetoed_round(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.0/10\nKey issues: severe\n"
            "TRIGGER-EVIDENCE FLAGS:\n- Population stat missing\n"
            "FLEET-SCOPE FLAGS:\n- Pre-prod excluded\n"
            "REGULATORY-NOTIFY FLAGS:\n- Canada missing\n"
            "REVIEWER VETO: Under-scoped recall with CPSC clock already running."
        )
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.0, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "veto_reason" in result.metadata
        assert result.metadata["trigger_evidence_flags"] != []
        assert result.metadata["fleet_scope_flags"] != []
        assert result.metadata["regulatory_notify_flags"] != []

    @pytest.mark.asyncio
    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "veto_reason" not in result.metadata


class TestRecallOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output


class TestRecallExtractVeto:
    def test_returns_none_when_directive_is_none(self) -> None:
        assert RecallScopeManufacturingWorkflow._extract_veto("REVIEWER VETO: None", 1000) is None

    def test_returns_directive_on_same_line(self) -> None:
        v = RecallScopeManufacturingWorkflow._extract_veto("REVIEWER VETO: escalate immediately", 1000)
        assert v is not None and "escalate" in v

    def test_returns_directive_on_continuation_lines(self) -> None:
        critique = "REVIEWER VETO:\nUnder-scoped recall with serious injury.\nRoute to safety committee."
        v = RecallScopeManufacturingWorkflow._extract_veto(critique, 1000)
        assert v is not None and "Under-scoped" in v and "safety committee" in v


class TestRecallRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Trigger summary:", "Evidence inventory:", "Fleet serial traceability:",
            "Adjacent product exposure:", "Regulatory context:", "Service capacity context:",
            "Proposed scope:",
        ]:
            assert fragment in text
