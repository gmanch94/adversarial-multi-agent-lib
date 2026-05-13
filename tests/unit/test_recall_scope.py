"""Unit tests for RecallScopeWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.retail.workflows.recall_scope import (
    RecallRequest,
    RecallScopeWorkflow,
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
    score: float,
    *,
    approved: bool,
    critique: str = "",
    suggestions: list[str] | None = None,
) -> ReviewResult:
    return ReviewResult(
        score=score,
        critique=critique,
        suggestions=suggestions or [],
        approved=approved,
    )


def make_request(**kwargs: Any) -> RecallRequest:
    defaults: dict[str, Any] = dict(
        contamination_signal=(
            "Supplier alert: positive Listeria culture on swab from production line 3 "
            "on 2026-05-08; tied to RTE chicken salad family."
        ),
        supplier_lot="LOT-CS-20260508-A,LOT-CS-20260508-B",
        product_skus="SKU-RTE-CKN-001 (12oz tub), SKU-RTE-CKN-002 (24oz tub)",
        distribution_window="Produced 2026-05-08; shipped 2026-05-09 through 2026-05-11",
        stores_in_scope=(
            "KRO-OH-0042, KRO-OH-0043, KRO-KY-0118, KRO-IN-0211, KRO-MI-0307 (5 stores)"
        ),
        consumer_exposure=(
            "Approx 1,840 units sold across 5 stores by 2026-05-13; loyalty-linked "
            "purchases: 612 (33%)."
        ),
        regulatory_context=(
            "FDA-regulated; 21 CFR Part 7 applies; state notifications required in OH, "
            "KY, IN, MI. Listeria triggers Class I recall by default."
        ),
        competing_evidence=(
            "Supplier disputes positive — claims swab cross-contamination during cleanup. "
            "Lab retest pending. No consumer illness reports as of 2026-05-13."
        ),
    )
    defaults.update(kwargs)
    return RecallRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> RecallScopeWorkflow:
    return RecallScopeWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Contamination Signal Summary
Supplier-detected Listeria positive on line 3 swab. Lab retest pending; supplier disputes.
Conservative scope pending retest.

## Recall Scope
Lots LOT-CS-20260508-A and LOT-CS-20260508-B; SKUs SKU-RTE-CKN-001 + SKU-RTE-CKN-002;
5 stores (KRO-OH-0042, KRO-OH-0043, KRO-KY-0118, KRO-IN-0211, KRO-MI-0307); window
2026-05-08 production / 2026-05-09 to 2026-05-11 ship.

## Evidence Basis
Lot list ← supplier swab positive on line 3 same day. Stores ← stores_in_scope.
Date window ← supplier-reported production + ship dates.

## Regulatory Actions
FDA notification within 24h per 21 CFR Part 7. State notifications: OH, KY, IN, MI.
Default Class I (Listeria).

## Consumer Communications
Press release (Class I default); in-store signage at all 5 stores; SMS to 612
loyalty-linked buyers.

## Operational Actions
Halt-sale order to all 5 stores. Pull from shelf within 4h. Hold remaining DC inventory.

## Evidence Gaps
Lab retest result not yet available; if negative, scope can shrink.

## Claims
[Source: supplier_lot] Two lots implicated: LOT-CS-20260508-A and LOT-CS-20260508-B.
[Source: stores_in_scope] Five stores received the implicated lots.
[Source: regulatory_context] Listeria recall defaults to Class I under 21 CFR Part 7.
"""


_CLEAN_CRITIQUE = """\
Solid plan.

Overall score: 8.5/10
Key issues:
- Pending lab retest could narrow scope.

SCOPE FLAGS: None detected
EVIDENCE FLAGS: None detected
REVIEWER VETO: None
"""


class TestRecallConvergence:
    @pytest.mark.asyncio
    async def test_converges_when_score_meets_threshold_and_no_flags_and_no_veto(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert result.final_score == 8.5
        assert "veto_reason" not in result.metadata

    @pytest.mark.asyncio
    async def test_does_not_converge_when_scope_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique_round1 = (
            "Overall score: 8.0/10\nKey issues: missing sibling lot\n"
            "SCOPE FLAGS:\n- Sibling lot LOT-CS-20260508-C (same line, same day) not in scope\n"
            "EVIDENCE FLAGS: None detected\nREVIEWER VETO: None"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer([
            make_result(8.0, approved=True, critique=critique_round1),
            make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE),
        ])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2
        assert any("Sibling lot" in f for f in result.metadata["scope_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_evidence_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 8.0/10\nKey issues: scope rests on inference\n"
            "SCOPE FLAGS: None detected\n"
            "EVIDENCE FLAGS:\n- Date window relies on supplier statement, not production records\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Date window" in f for f in result.metadata["evidence_flags"])


class TestRecallVeto:
    @pytest.mark.asyncio
    async def test_veto_halts_immediately_with_high_score(
        self, tmp_path: Path
    ) -> None:
        veto_critique = (
            "Overall score: 9.0/10\nKey issues: comms missing\n"
            "SCOPE FLAGS: None detected\nEVIDENCE FLAGS: None detected\n"
            "REVIEWER VETO: Life-safety Listeria signal with no consumer notification path; "
            "escalate to safety officer before any operational action."
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(9.0, approved=True, critique=veto_critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert result.final_score == 9.0
        assert "veto_reason" in result.metadata
        assert "Life-safety" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert _VETO_BANNER in result.output

    @pytest.mark.asyncio
    async def test_veto_records_flags_from_vetoed_round(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: many\n"
            "SCOPE FLAGS:\n- Missing sibling lot\n"
            "EVIDENCE FLAGS:\n- Date window inferred\n"
            "REVIEWER VETO: Recall halts sale but does not pull from shelf — escalate."
        )
        config = make_config(tmp_path, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert "veto_reason" in result.metadata
        assert result.metadata["scope_flags"] != []
        assert result.metadata["evidence_flags"] != []

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

    @pytest.mark.asyncio
    async def test_metadata_keys_present(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        for key in (
            "supplier_lot",
            "scope_flags",
            "evidence_flags",
            "safety_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata

    @pytest.mark.asyncio
    async def test_claims_registered(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        # Three claims in _GOOD_OUTPUT
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestExtractFlags:
    def test_extracts_scope_flags(self) -> None:
        critique = (
            "Overall score: 7/10\nKey issues: x\n"
            "SCOPE FLAGS:\n- Lot LOT-X missing\n- Store KRO-X missing\n"
            "EVIDENCE FLAGS: None detected\nREVIEWER VETO: None"
        )
        flags = RecallScopeWorkflow._extract_flags(critique, "SCOPE FLAGS:")
        assert len(flags) == 2
        assert any("LOT-X" in f for f in flags)

    def test_extracts_evidence_flags_stops_at_veto(self) -> None:
        critique = (
            "SCOPE FLAGS: None detected\n"
            "EVIDENCE FLAGS:\n- No primary lab evidence\n"
            "REVIEWER VETO: Some directive that mentions evidence."
        )
        flags = RecallScopeWorkflow._extract_flags(critique, "EVIDENCE FLAGS:")
        assert len(flags) == 1
        assert "No primary lab evidence" in flags[0]

    def test_returns_empty_when_none_detected(self) -> None:
        flags = RecallScopeWorkflow._extract_flags(
            "SCOPE FLAGS: None detected\nEVIDENCE FLAGS: None detected", "SCOPE FLAGS:"
        )
        assert flags == []

    def test_returns_empty_when_header_absent(self) -> None:
        assert RecallScopeWorkflow._extract_flags("clean.", "SCOPE FLAGS:") == []


class TestExtractVeto:
    def test_returns_none_when_directive_is_none(self) -> None:
        veto = RecallScopeWorkflow._extract_veto("REVIEWER VETO: None", 1000)
        assert veto is None

    def test_returns_directive_on_same_line(self) -> None:
        veto = RecallScopeWorkflow._extract_veto(
            "REVIEWER VETO: escalate immediately, life-safety risk", 1000
        )
        assert veto is not None
        assert "escalate immediately" in veto

    def test_returns_directive_on_continuation_lines(self) -> None:
        critique = (
            "REVIEWER VETO:\n"
            "Life-safety pathogen with no regulator contact.\n"
            "Escalate to safety officer."
        )
        veto = RecallScopeWorkflow._extract_veto(critique, 1000)
        assert veto is not None
        assert "Life-safety" in veto
        assert "Escalate" in veto

    def test_returns_none_when_header_absent(self) -> None:
        assert RecallScopeWorkflow._extract_veto("clean.", 1000) is None

    def test_truncates_to_max_chars(self) -> None:
        critique = "REVIEWER VETO: " + "x" * 5000
        veto = RecallScopeWorkflow._extract_veto(critique, 200)
        assert veto is not None
        assert len(veto) == 200


class TestRecallRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        for fragment in [
            "Contamination signal:",
            "Supplier lot:",
            "Product SKUs:",
            "Distribution window:",
            "Stores in scope:",
            "Consumer exposure:",
            "Regulatory context:",
            "Competing evidence:",
        ]:
            assert fragment in text
