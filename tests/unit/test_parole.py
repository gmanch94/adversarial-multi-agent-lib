"""
Unit tests for ParoleAssessmentWorkflow — no live API calls.

Pattern mirrors test_review_loop.py: FakeExecutor + FakeReviewer injected
through BaseWorkflow.__init__, Config uses test keys and tmp_path.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core._internal import extract_flags
from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.parole.workflows.parole import (
    ParoleAssessmentWorkflow,
    ParoleCase,
    _DISCLAIMER,
)

from .fakes import FakeExecutor, FakeReviewer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


def make_case(**kwargs: Any) -> ParoleCase:
    defaults: dict[str, Any] = dict(
        case_id="TEST-001",
        offense_description="Residential burglary, no violence.",
        sentence_imposed="4 years",
        time_served="3 years",
        in_custody_conduct="No incidents in the last 18 months.",
        programs_completed="GED (month 20), CBT (month 24).",
        psychological_assessment="Low PCL-R score; substance-use disorder in remission.",
        reentry_plan="Transitional housing confirmed. Employment offer pending parole.",
    )
    defaults.update(kwargs)
    return ParoleCase(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> ParoleAssessmentWorkflow:
    return ParoleAssessmentWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Risk Analysis
No unresolved risk factors.

## Rehabilitation Evidence
GED and CBT completed.

## Reentry Plan Assessment
Housing and employment confirmed.

## Advisory Recommendation
Conditional Grant — strong rehabilitation evidence and concrete reentry plan.

## Conditions If Granted
- Weekly check-ins with parole officer.
- Continued outpatient substance-use counselling.

## Evidence Gaps
No actuarial risk score available.

## Claims
[Source: programs_completed] Individual completed GED in month 20.
[Source: programs_completed] CBT completed in month 24.
"""


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------


class TestConvergence:
    @pytest.mark.asyncio
    async def test_converges_when_score_meets_threshold_and_no_bias(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="BIAS FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        assert result.converged is True
        assert result.rounds == 1
        assert result.final_score == 8.0

    @pytest.mark.asyncio
    async def test_does_not_converge_when_bias_flags_present(
        self, tmp_path: Path
    ) -> None:
        """Score ≥ threshold but bias flags present: must keep iterating."""
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=2)
        # Round 1: high score but bias; Round 2: high score, no bias
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    8.0,
                    approved=True,
                    critique="BIAS FLAGS:\n- Used neighbourhood as risk proxy",
                ),
                make_result(8.0, approved=True, critique="BIAS FLAGS: None detected"),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        assert result.converged is True
        assert result.rounds == 2  # required a second round to clear bias

    @pytest.mark.asyncio
    async def test_does_not_converge_when_score_below_threshold(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(6.0, approved=False, critique="Needs more balance."),
                make_result(6.5, approved=False, critique="Still one-sided."),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        assert result.converged is False
        assert result.rounds == 2

    @pytest.mark.asyncio
    async def test_reaches_max_rounds_without_convergence(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=9.0, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT] * 3)
        reviewer = FakeReviewer(
            [make_result(7.0, approved=False)] * 3
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        assert result.converged is False
        assert result.rounds == 3


# ---------------------------------------------------------------------------
# Output structure
# ---------------------------------------------------------------------------


class TestOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="BIAS FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_metadata_keys_present(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="BIAS FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        assert "case_id" in result.metadata
        assert "recommendation" in result.metadata
        assert "bias_flags" in result.metadata
        assert "board_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata

    @pytest.mark.asyncio
    async def test_case_id_in_metadata(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="BIAS FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case(case_id="CASE-XYZ"))

        assert result.metadata["case_id"] == "CASE-XYZ"

    @pytest.mark.asyncio
    async def test_recommendation_extracted(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="BIAS FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        rec = result.metadata["recommendation"]
        assert isinstance(rec, str)
        assert len(rec) > 0
        # The good output has "Conditional Grant" in the recommendation section
        assert "Conditional Grant" in rec

    @pytest.mark.asyncio
    async def test_board_checklist_is_nonempty_list(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="BIAS FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        checklist = result.metadata["board_checklist"]
        assert isinstance(checklist, list)
        assert len(checklist) >= 5  # at minimum the standard items


# ---------------------------------------------------------------------------
# Bias flag handling
# ---------------------------------------------------------------------------


class TestBiasFlags:
    @pytest.mark.asyncio
    async def test_bias_flags_accumulated_across_rounds(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    7.0,
                    approved=False,
                    critique="BIAS FLAGS:\n- ZIP code used as proxy",
                ),
                make_result(
                    8.0,
                    approved=True,
                    critique="BIAS FLAGS: None detected",
                ),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        # Exact accumulated list — a slurp or wiring regression in the private
        # parser fails here instead of passing on membership (F2).
        assert result.metadata["bias_flags"] == ["ZIP code used as proxy"]

    @pytest.mark.asyncio
    async def test_no_bias_flags_when_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="BIAS FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        assert result.metadata["bias_flags"] == []

    @pytest.mark.asyncio
    async def test_bias_flag_triggers_warning_in_checklist(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    7.0,
                    approved=False,
                    critique="BIAS FLAGS:\n- Family history used as proxy",
                ),
                make_result(8.5, approved=True, critique="BIAS FLAGS: None detected"),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)

        result = await workflow.run(case=make_case())

        checklist = result.metadata["board_checklist"]
        # Bias warning should be the first item in the checklist
        assert "BIAS FLAGS DETECTED" in checklist[0]


# ---------------------------------------------------------------------------
# Claim ledger
# ---------------------------------------------------------------------------


class TestClaimLedger:
    @pytest.mark.asyncio
    async def test_claims_registered_in_ledger(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="BIAS FLAGS: None detected")]
        )
        ledger = ClaimLedger(str(tmp_path / "ledger.json"))
        workflow = ParoleAssessmentWorkflow(
            config=config,
            executor=executor,
            reviewer=reviewer,
            ledger=ledger,
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )

        await workflow.run(case=make_case())

        all_claims = ledger.all()
        assert len(all_claims) >= 2  # at least the two claims in _GOOD_OUTPUT


# ---------------------------------------------------------------------------
# bias-flag extraction (shared extract_flags helper)
# ---------------------------------------------------------------------------


class TestExtractBiasFlags:
    """Bias-flag extraction delegates to the shared ``extract_flags`` helper
    (F1 follow-up migration off the private parser). Assertions are exact so a
    slurp or wiring regression fails instead of passing on membership."""

    def test_extracts_flags_from_critique(self) -> None:
        critique = (
            "Good balance.\n\nBIAS FLAGS:\n"
            "- Neighbourhood used as risk proxy\n"
            "- Family history mentioned\n"
            "\nOverall score: 6/10"
        )
        flags = extract_flags(critique, "BIAS FLAGS:")
        assert flags == [
            "Neighbourhood used as risk proxy",
            "Family history mentioned",
        ]

    def test_returns_empty_when_none_detected(self) -> None:
        critique = "Good balance.\n\nBIAS FLAGS: None detected\n\nOverall score: 8/10"
        assert extract_flags(critique, "BIAS FLAGS:") == []

    def test_returns_empty_when_section_absent(self) -> None:
        critique = "No issues found. Overall score: 9/10"
        assert extract_flags(critique, "BIAS FLAGS:") == []

    def test_stops_at_next_section(self) -> None:
        critique = "BIAS FLAGS:\n- One flag\nOverall score: 5/10\nKey issues: none"
        assert extract_flags(critique, "BIAS FLAGS:") == ["One flag"]

    def test_stops_at_sibling_header(self) -> None:
        # Inherited H-IND-1 protection the private parser lacked: a sibling
        # uppercase header terminates the section instead of being slurped.
        critique = "BIAS FLAGS:\n- proxy used\nFAIRNESS FLAGS:\n- uneven"
        assert extract_flags(critique, "BIAS FLAGS:") == ["proxy used"]

    def test_handles_bullet_variants(self) -> None:
        critique = "BIAS FLAGS:\n• bullet one\n* bullet two\n- bullet three\n"
        assert extract_flags(critique, "BIAS FLAGS:") == [
            "bullet one",
            "bullet two",
            "bullet three",
        ]


# ---------------------------------------------------------------------------
# ParoleCase.to_prompt_text
# ---------------------------------------------------------------------------


class TestParoleCaseToPromptText:
    def test_contains_all_required_fields(self) -> None:
        case = make_case()
        text = case.to_prompt_text()
        assert "Case ID: TEST-001" in text
        assert "Offense:" in text
        assert "Sentence imposed:" in text
        assert "Time served:" in text
        assert "In-custody conduct:" in text
        assert "Programs completed:" in text
        assert "Psychological assessment:" in text
        assert "Reentry plan:" in text

    def test_omits_optional_fields_when_empty(self) -> None:
        case = make_case()  # victim_statement="" and external_risk_score=""
        text = case.to_prompt_text()
        assert "Victim statement:" not in text
        assert "External risk score:" not in text

    def test_includes_optional_fields_when_set(self) -> None:
        case = make_case(
            victim_statement="Victim objects to release.",
            external_risk_score="ORAS-PT: 14/45 (Low-Moderate)",
        )
        text = case.to_prompt_text()
        assert "Victim statement:" in text
        assert "External risk score:" in text
