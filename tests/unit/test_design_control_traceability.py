"""Unit tests for DesignControlTraceabilityWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.design_control_traceability import (
    DesignControlRequest,
    DesignControlTraceabilityWorkflow,
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


def make_request(**kwargs: Any) -> DesignControlRequest:
    defaults: dict[str, Any] = dict(
        device_description="Continuous glucose monitor: subcutaneous sensor, "
                           "transmitter, and receiver app for 14-day wear.",
        design_inputs="DI-01 accuracy MARD <= 10%; DI-02 14-day sensor life; "
                      "DI-03 alert on hypoglycemia < 70 mg/dL; DI-04 biocompatible adhesive",
        design_outputs="DO-01 sensor spec rev C; DO-02 transmitter firmware v2.1; "
                       "DO-03 alert logic spec; DO-04 adhesive material spec",
        verification_evidence="VER-01 bench accuracy report; VER-02 accelerated wear test; "
                             "VER-03 alert-threshold unit test log",
        validation_evidence="VAL-01 30-subject clinical use study meets intended use",
        risk_analysis_reference="RMF-2026-014 (ISO 14971); hazard H-03 missed hypo alert",
        design_review_records="DR-1 inputs frozen 2026-01; DR-2 outputs approved 2026-03",
        trace_matrix_summary="DI-01->DO-01->VER-01; DI-02->DO-01->VER-02; "
                            "DI-03->DO-03->VER-03->VAL-01; DI-04 unlinked",
    )
    defaults.update(kwargs)
    return DesignControlRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        request = make_request()
        text = request.to_prompt_text()
        assert "Device description:" in text
        assert "Design inputs:" in text
        assert "Design outputs:" in text
        assert "Verification evidence:" in text
        assert "Validation evidence:" in text
        assert "Risk analysis reference:" in text
        assert "Design review records:" in text
        assert "Trace matrix summary:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        request = make_request(design_inputs=oversized)
        text = request.to_prompt_text()
        section = text.split("Design inputs:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Traceability matrix summary\nAll links resolve"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="TRACE-GAP FLAGS: None detected\n"
                         "VERIFICATION FLAGS: None detected\n"
                         "VALIDATION FLAGS: None detected",
            )
        ])
        wf = DesignControlTraceabilityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_trace_gap_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: orphan input\n"
            "TRACE-GAP FLAGS:\n- Design input DI-04 has no linked design output\n"
            "VERIFICATION FLAGS: None detected\n"
            "VALIDATION FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = DesignControlTraceabilityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["trace_gap_flags"] == [
            "Design input DI-04 has no linked design output"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "TRACE-GAP FLAGS:\n- Orphan output DO-11\n"
            "VERIFICATION FLAGS: None detected\n"
            "VALIDATION FLAGS: None detected\n"
            "RECOMMENDATION: schedule a design review\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = DesignControlTraceabilityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.metadata["trace_gap_flags"] == ["Orphan output DO-11"]

    async def test_does_not_converge_when_verification_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "TRACE-GAP FLAGS: None detected\n"
            "VERIFICATION FLAGS:\n- DO-02 asserted verified with no cited evidence\n"
            "VALIDATION FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = DesignControlTraceabilityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["verification_flags"] == [
            "DO-02 asserted verified with no cited evidence"
        ]

    async def test_does_not_converge_when_validation_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "TRACE-GAP FLAGS: None detected\n"
            "VERIFICATION FLAGS: None detected\n"
            "VALIDATION FLAGS:\n- User need UN-02 lacks design-validation evidence\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = DesignControlTraceabilityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["validation_flags"] == [
            "User need UN-02 lacks design-validation evidence"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="TRACE-GAP FLAGS:\n- DI-04 orphan\n"
                         "VERIFICATION FLAGS: None detected\n"
                         "VALIDATION FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="TRACE-GAP FLAGS: None detected\n"
                         "VERIFICATION FLAGS: None detected\n"
                         "VALIDATION FLAGS: None detected",
            ),
        ])
        wf = DesignControlTraceabilityWorkflow(
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
                critique="TRACE-GAP FLAGS: None detected\n"
                         "VERIFICATION FLAGS: None detected\n"
                         "VALIDATION FLAGS: None detected",
            )
        ])
        wf = DesignControlTraceabilityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert "trace_gap_flags" in result.metadata
        assert "verification_flags" in result.metadata
        assert "validation_flags" in result.metadata
        assert "design_control_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata
        checklist = result.metadata["design_control_checklist"]
        assert checklist[0] == "[OWNER: Design Assurance / Quality Engineering]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="TRACE-GAP FLAGS: None detected\n"
                         "VERIFICATION FLAGS: None detected\n"
                         "VALIDATION FLAGS: None detected",
            )
        ])
        wf = DesignControlTraceabilityWorkflow(
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
            "TRACE-GAP FLAGS: None detected\n"
            "VERIFICATION FLAGS: None detected\n"
            "VALIDATION FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = DesignControlTraceabilityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
