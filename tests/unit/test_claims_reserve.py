"""Unit tests for ClaimsReserveWorkflow — no live API calls.

Mirrors test_recall_scope.py structure (D-PC-5). Covers:
- convergence on clean input
- non-convergence per flag class (RESERVE / PRECEDENT / LITIGATION)
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
from adv_multi_agent.pc.workflows.claims_reserve import (
    ClaimsReserveRequest,
    ClaimsReserveWorkflow,
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


def make_request(**kwargs: Any) -> ClaimsReserveRequest:
    defaults: dict[str, Any] = dict(
        loss_event=(
            "2026-04-18 — slip-and-fall at named insured premises, Hamilton County OH; "
            "claimant 47F retail associate."
        ),
        injury_or_damage=(
            "TBI tier severe; Glasgow 11 at admission; persistent cognitive deficit; "
            "partial permanent disability likely."
        ),
        coverage_summary=(
            "GL CG 00 01 04 13. Per-occurrence $1M / aggregate $2M. SIR $25k exhausted. "
            "No umbrella."
        ),
        comparable_cases=(
            "Hamilton OH 2024 settlement $725k (peer facts). Hamilton OH 2023 verdict "
            "$1.1M. Franklin OH 2024 settlement $540k. Cuyahoga OH 2022 verdict $1.4M. "
            "Venue-matched median ~$725k."
        ),
        venue="Hamilton County OH Court of Common Pleas; moderate-plaintiff-friendly.",
        defense_posture=(
            "Liability likely admitted; quantum dispute. Claimant 10% comparative fault. "
            "Ohio modified comparative-fault (51% bar)."
        ),
        medical_or_repair_estimate=(
            "Specials $86k; future medical $240k; future LEC $190k PV; non-economic cap "
            "may not apply if catastrophic exception granted."
        ),
        regulatory_exposure=(
            "No state AG / DOI inquiry. Single claimant. Plaintiff signalled cap-exception "
            "argument."
        ),
        current_reserve_proposal=(
            "Indemnity $620k; defence $95k (15% of indemnity); IBNR not stated. Total $715k."
        ),
    )
    defaults.update(kwargs)
    return ClaimsReserveRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> ClaimsReserveWorkflow:
    return ClaimsReserveWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Loss Event Summary
Slip-and-fall premises liability, Hamilton County OH; severe TBI; named insured GreenLeaf.

## Coverage Analysis
GL CG 00 01 04 13; per-occurrence $1M; SIR exhausted. No coverage-defense issue identified.

## Indemnity Reserve
Proposed $750,000 (Hamilton + Franklin median $725k; +3% upward for permanent-disability tier).

## Defence-Cost Reserve
Proposed $180,000 (24% of indemnity; Moderate-complexity tier per Methodology A).

## IBNR Uplift
Applied 1.12 LDF for GL premises 18-month age tier + 4% severity trend over 14 expected months.
Combined uplift: ~16%.

## Venue & Posture Adjustment
Hamilton OH: moderate plaintiff-friendly; +5% on anchor. Comparative fault −10%. Math:
$725k × 1.03 × 1.05 × 0.90 ≈ $706k → rounded to $750k for the catastrophic-exception upside.

## Regulatory & Aggregate Exposure
Single claimant; no aggregate provision required. No state AG / DOI signal.

## Treaty & Reinsurance Notification
Below treaty notification threshold ($1M for this LOB).

## Evidence Gaps
Catastrophic-exception ruling not yet decided; if granted, expand indemnity range to $1.0–1.2M.

## Claims
[Source: comparable_cases] Hamilton/Franklin venue-matched median is approximately $725,000.
[Source: defense_posture] Ohio modified comparative-fault rule applies with 10% claimant fault.
[Source: regulatory_exposure] No aggregate or regulatory-defence provision required.
"""


_CLEAN_CRITIQUE = """\
Reserve is defensible.

Overall score: 8.5/10
Key issues:
- Catastrophic-exception ruling could materially expand range.

RESERVE FLAGS: None detected
PRECEDENT FLAGS: None detected
LITIGATION FLAGS: None detected
REVIEWER VETO: None
"""


class TestReserveConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert result.final_score == 8.5
        assert "veto_reason" not in result.metadata

    @pytest.mark.asyncio
    async def test_does_not_converge_when_reserve_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: defence reserve light\n"
            "RESERVE FLAGS:\n- Defence reserve at 15% is below complex-tier 30% floor\n"
            "PRECEDENT FLAGS: None detected\n"
            "LITIGATION FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Defence" in f for f in result.metadata["reserve_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_precedent_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: stale comparables\n"
            "RESERVE FLAGS: None detected\n"
            "PRECEDENT FLAGS:\n- Cuyahoga 2022 verdict is wrong venue\n"
            "LITIGATION FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Cuyahoga" in f for f in result.metadata["precedent_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_litigation_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.0/10\nKey issues: venue posture missing\n"
            "RESERVE FLAGS: None detected\n"
            "PRECEDENT FLAGS: None detected\n"
            "LITIGATION FLAGS:\n- Cap-exception risk not reflected in upper range\n"
            "REVIEWER VETO: None"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Cap-exception" in f for f in result.metadata["litigation_flags"])


class TestReserveVeto:
    @pytest.mark.asyncio
    async def test_veto_halts_immediately_with_high_score(
        self, tmp_path: Path
    ) -> None:
        veto_critique = (
            "Overall score: 9.0/10\nKey issues: structural\n"
            "RESERVE FLAGS: None detected\n"
            "PRECEDENT FLAGS: None detected\n"
            "LITIGATION FLAGS: None detected\n"
            "REVIEWER VETO: Catastrophic-TBI signal with proposed indemnity below $500k "
            "and no defence-cost provision; escalate to senior actuary before booking."
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(9.0, approved=True, critique=veto_critique)]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert result.final_score == 9.0
        assert "veto_reason" in result.metadata
        assert "Catastrophic" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert _VETO_BANNER in result.output

    @pytest.mark.asyncio
    async def test_veto_records_flags_from_vetoed_round(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 6.0/10\nKey issues: structural\n"
            "RESERVE FLAGS:\n- IBNR not stated\n"
            "PRECEDENT FLAGS:\n- Wrong-venue comparable cited\n"
            "LITIGATION FLAGS:\n- Cap-exception risk not modelled\n"
            "REVIEWER VETO: Catastrophic-TBI but reserve below comparable median; "
            "escalate to claims committee."
        )
        config = make_config(tmp_path, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.0, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert "veto_reason" in result.metadata
        assert result.metadata["reserve_flags"] != []
        assert result.metadata["precedent_flags"] != []
        assert result.metadata["litigation_flags"] != []

    @pytest.mark.asyncio
    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "veto_reason" not in result.metadata


class TestReserveOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered_into_ledger(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.5, approved=True, critique=_CLEAN_CRITIQUE)]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        # _GOOD_OUTPUT has 3 bullet claims under ## Claims.
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestExtractVeto:
    def test_returns_none_when_directive_is_none(self) -> None:
        assert ClaimsReserveWorkflow._extract_veto("REVIEWER VETO: None", 1000) is None

    def test_returns_directive_on_same_line(self) -> None:
        veto = ClaimsReserveWorkflow._extract_veto(
            "REVIEWER VETO: escalate immediately, catastrophic-injury exposure", 1000
        )
        assert veto is not None
        assert "escalate immediately" in veto

    def test_returns_directive_on_continuation_lines(self) -> None:
        critique = (
            "REVIEWER VETO:\n"
            "Catastrophic-TBI signal with under-reserve.\n"
            "Route to senior actuary."
        )
        veto = ClaimsReserveWorkflow._extract_veto(critique, 1000)
        assert veto is not None
        assert "Catastrophic" in veto
        assert "senior actuary" in veto

    def test_sibling_header_stops_capture(self) -> None:
        critique = (
            "REVIEWER VETO:\n"
            "Real directive line\n"
            "PRECEDENT FLAGS:\n"
            "- not part of veto"
        )
        veto = ClaimsReserveWorkflow._extract_veto(critique, 1000)
        assert veto is not None
        assert "Real directive" in veto
        assert "PRECEDENT" not in veto

    def test_marker_on_first_line_then_continuation_directive(self) -> None:
        critique = (
            "REVIEWER VETO: none detected\n"
            "On reflection — escalate to claims committee for cap-exception ruling."
        )
        veto = ClaimsReserveWorkflow._extract_veto(critique, 1000)
        assert veto is not None
        assert "escalate" in veto.lower()


class TestClaimsReserveRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        for fragment in [
            "Loss event:",
            "Injury / damage:",
            "Coverage summary:",
            "Comparable cases:",
            "Venue:",
            "Defense posture:",
            "Medical / repair estimate:",
            "Regulatory exposure:",
            "Current reserve proposal:",
        ]:
            assert fragment in text
