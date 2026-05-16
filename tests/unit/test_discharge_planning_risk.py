"""Unit tests for DischargePlanningRiskWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.healthcare.workflows.discharge_planning_risk import (
    DischargePlanningRiskWorkflow,
    DischargePlanningRequest,
    _DISCLAIMER,
    _MAX_FIELD_CHARS,
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


def make_review(
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


def make_request(**kwargs: Any) -> DischargePlanningRequest:
    defaults: dict[str, Any] = dict(
        patient_summary=(
            "78yo F with CHF (EF 30%), HTN, DM2. Lives alone in apartment, "
            "no family nearby. Primary language English."
        ),
        hospitalization_summary=(
            "Admitted for CHF exacerbation with volume overload. Diuresed with "
            "IV furosemide, euvolemic by day 3. LOS 5 days."
        ),
        proposed_discharge_plan=(
            "Discharge to home with home health nursing 3x/week. "
            "Follow-up cardiologist in 7 days. Resume home medications."
        ),
        social_determinants=(
            "Lives alone; no transportation for follow-up appointments. "
            "Food-security concern — relies on community meals program. "
            "Medicare + Medicaid dual-eligible."
        ),
        readmission_history=(
            "Two CHF admissions in past 12 months (30-day readmission after "
            "prior discharge). LACE score 14 (high risk)."
        ),
        care_team_notes=(
            "PT/OT: functional baseline restored, safe for home. "
            "SW: transportation barrier identified; Meals on Wheels enrolled. "
            "Nursing: patient education on daily weights completed."
        ),
    )
    defaults.update(kwargs)
    return DischargePlanningRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        request = make_request()
        text = request.to_prompt_text()
        assert "Patient summary:" in text
        assert "Hospitalization summary:" in text
        assert "Proposed discharge plan:" in text
        assert "Social determinants:" in text
        assert "Readmission history:" in text
        assert "Care team notes:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        request = make_request(patient_summary=oversized)
        text = request.to_prompt_text()
        patient_section = text.split("Patient summary:")[1].split("\n")[0]
        assert len(patient_section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_on_first_round_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Discharge plan\nHome with home health."])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique=(
                    "READMISSION FLAGS: None detected\n"
                    "CARE-GAP FLAGS: None detected\n"
                    "SOCIAL-DETERMINANT FLAGS: None detected"
                ),
            )
        ])
        wf = DischargePlanningRiskWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_with_readmission_flag(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2", "draft 3"])
        critique_with_flag = (
            "READMISSION FLAGS:\n"
            "  - No 48-hour phone follow-up scheduled despite LACE score 14\n"
            "CARE-GAP FLAGS: None detected\n"
            "SOCIAL-DETERMINANT FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(9.0, approved=True, critique=critique_with_flag),
            make_review(9.0, approved=True, critique=critique_with_flag),
            make_review(9.0, approved=True, critique=critique_with_flag),
        ])
        wf = DischargePlanningRiskWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3  # max_review_rounds

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique=(
                    "READMISSION FLAGS:\n  - Missing 48-hour phone follow-up\n"
                    "CARE-GAP FLAGS: None detected\n"
                    "SOCIAL-DETERMINANT FLAGS: None detected"
                ),
            ),
            make_review(
                9.0, approved=True,
                critique=(
                    "READMISSION FLAGS: None detected\n"
                    "CARE-GAP FLAGS: None detected\n"
                    "SOCIAL-DETERMINANT FLAGS: None detected"
                ),
            ),
        ])
        wf = DischargePlanningRiskWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique=(
                    "READMISSION FLAGS: None detected\n"
                    "CARE-GAP FLAGS: None detected\n"
                    "SOCIAL-DETERMINANT FLAGS: None detected"
                ),
            )
        ])
        wf = DischargePlanningRiskWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert "readmission_flags" in result.metadata
        assert "care_gap_flags" in result.metadata
        assert "social_determinant_flags" in result.metadata
        assert "discharge_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique=(
                    "READMISSION FLAGS: None detected\n"
                    "CARE-GAP FLAGS: None detected\n"
                    "SOCIAL-DETERMINANT FLAGS: None detected"
                ),
            )
        ])
        wf = DischargePlanningRiskWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
        assert "ADVISORY" in _DISCLAIMER.upper()


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    """L-HEALTH-3: zero flags but approved=False (score below threshold) must not converge."""

    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        clean_critique = (
            "READMISSION FLAGS: None detected\n"
            "CARE-GAP FLAGS: None detected\n"
            "SOCIAL-DETERMINANT FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = DischargePlanningRiskWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
