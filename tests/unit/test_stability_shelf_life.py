"""Unit tests for StabilityShelfLifeWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.stability_shelf_life import (
    StabilityShelfLifeRequest,
    StabilityShelfLifeWorkflow,
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


def make_request(**kwargs: Any) -> StabilityShelfLifeRequest:
    defaults: dict[str, Any] = dict(
        product_description="Oral solid-dose immediate-release tablet in "
                           "HDPE bottles with desiccant.",
        proposed_shelf_life="36 months at 25C/60%RH.",
        storage_conditions="Long-term 25C/60%RH; accelerated 40C/75%RH.",
        stability_data_summary="3 primary batches; 0/3/6/9/12-month long-term; "
                            "0/3/6-month accelerated; assay, dissolution, impurities.",
        specification_limits="Assay 95.0-105.0%; total impurities <= 1.0%; "
                          "dissolution Q >= 80% at 30 min.",
        trend_analysis_summary="Assay shows a slight downward drift over 12 months; "
                            "impurities stable.",
        oos_oot_events="No OOS; one borderline dissolution OOT investigated and closed.",
        extrapolation_basis="Caller proposes 36 months from 12 months long-term plus "
                        "6 months accelerated data.",
    )
    defaults.update(kwargs)
    return StabilityShelfLifeRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        assert "Product description:" in text
        assert "Proposed shelf life:" in text
        assert "Storage conditions:" in text
        assert "Stability data summary:" in text
        assert "Specification limits:" in text
        assert "Trend analysis summary:" in text
        assert "OOS/OOT events:" in text
        assert "Extrapolation basis:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(stability_data_summary=oversized).to_prompt_text()
        section = text.split("Stability data summary:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Extrapolation justification\nSupported"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="EXTRAPOLATION FLAGS: None detected\n"
                         "TREND FLAGS: None detected\n"
                         "SPEC-EXCEEDANCE FLAGS: None detected",
            )
        ])
        wf = StabilityShelfLifeWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_extrapolation_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: over-extrapolation\n"
            "EXTRAPOLATION FLAGS:\n"
            "- 36-month claim extrapolates beyond ICH Q1E limit for 12 months real-time data\n"
            "TREND FLAGS: None detected\n"
            "SPEC-EXCEEDANCE FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = StabilityShelfLifeWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["extrapolation_flags"] == [
            "36-month claim extrapolates beyond ICH Q1E limit for 12 months real-time data"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "EXTRAPOLATION FLAGS:\n- 36-month claim over-extrapolates\n"
            "TREND FLAGS: None detected\n"
            "SPEC-EXCEEDANCE FLAGS: None detected\n"
            "RECOMMENDATION: shorten to 24 months\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = StabilityShelfLifeWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.metadata["extrapolation_flags"] == ["36-month claim over-extrapolates"]

    async def test_does_not_converge_when_trend_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "EXTRAPOLATION FLAGS: None detected\n"
            "TREND FLAGS:\n- Assay downward drift ignored in the shelf-life claim\n"
            "SPEC-EXCEEDANCE FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = StabilityShelfLifeWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["trend_flags"] == [
            "Assay downward drift ignored in the shelf-life claim"
        ]

    async def test_does_not_converge_when_spec_exceedance_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "EXTRAPOLATION FLAGS: None detected\n"
            "TREND FLAGS: None detected\n"
            "SPEC-EXCEEDANCE FLAGS:\n- 12-month dissolution below Q treated as passing\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = StabilityShelfLifeWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["spec_exceedance_flags"] == [
            "12-month dissolution below Q treated as passing"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="EXTRAPOLATION FLAGS:\n- 36-month over-extrapolates\n"
                         "TREND FLAGS: None detected\n"
                         "SPEC-EXCEEDANCE FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="EXTRAPOLATION FLAGS: None detected\n"
                         "TREND FLAGS: None detected\n"
                         "SPEC-EXCEEDANCE FLAGS: None detected",
            ),
        ])
        wf = StabilityShelfLifeWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_keys_and_checklist_owner(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="EXTRAPOLATION FLAGS: None detected\n"
                         "TREND FLAGS: None detected\n"
                         "SPEC-EXCEEDANCE FLAGS: None detected",
            )
        ])
        wf = StabilityShelfLifeWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert "extrapolation_flags" in result.metadata
        assert "trend_flags" in result.metadata
        assert "spec_exceedance_flags" in result.metadata
        assert "stability_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata
        checklist = result.metadata["stability_checklist"]
        assert checklist[0] == "[OWNER: Stability / Analytical Sciences Lead]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="EXTRAPOLATION FLAGS: None detected\n"
                         "TREND FLAGS: None detected\n"
                         "SPEC-EXCEEDANCE FLAGS: None detected",
            )
        ])
        wf = StabilityShelfLifeWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
        assert "ADVISORY" in _DISCLAIMER.upper()


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    """Zero flags but approved=False (score below threshold) must not converge."""

    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        clean_critique = (
            "EXTRAPOLATION FLAGS: None detected\n"
            "TREND FLAGS: None detected\n"
            "SPEC-EXCEEDANCE FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = StabilityShelfLifeWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
