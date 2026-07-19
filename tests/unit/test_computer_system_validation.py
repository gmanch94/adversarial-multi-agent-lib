"""Unit tests for ComputerSystemValidationWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.computer_system_validation import (
    ComputerSystemValidationRequest,
    ComputerSystemValidationWorkflow,
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


def make_request(**kwargs: Any) -> ComputerSystemValidationRequest:
    defaults: dict[str, Any] = dict(
        system_description="Cloud-hosted eQMS module managing deviations and "
                           "CAPA records for a GMP manufacturing site.",
        intended_use_statement="Manage GxP deviation and CAPA records with "
                             "electronic signatures under 21 CFR Part 11.",
        gamp_category="Caller claims GAMP Category 4 (configured product).",
        requirements_summary="URS-010 e-signature; URS-012 audit trail; "
                           "URS-014 configurable approval routing; URS-016 role model",
        risk_assessment_summary="High patient-impact for CAPA effectiveness; "
                             "medium for routing configuration.",
        test_evidence_summary="OQ-010 e-signature executed; OQ-012 audit trail "
                            "executed; PQ-001 end-to-end executed",
        trace_matrix_summary="URS-010->OQ-010; URS-012->OQ-012; "
                          "URS-014 unlinked; URS-016->PQ-001",
        change_control_summary="Validated state under change control CC-2026-031.",
    )
    defaults.update(kwargs)
    return ComputerSystemValidationRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        assert "System description:" in text
        assert "Intended use statement:" in text
        assert "GAMP category:" in text
        assert "Requirements summary:" in text
        assert "Risk assessment summary:" in text
        assert "Test evidence summary:" in text
        assert "Trace matrix summary:" in text
        assert "Change control summary:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(requirements_summary=oversized).to_prompt_text()
        section = text.split("Requirements summary:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Intended-use and risk fit\nScope matches"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="INTENDED-USE FLAGS: None detected\n"
                         "TRACE-GAP FLAGS: None detected\n"
                         "TEST-EVIDENCE FLAGS: None detected",
            )
        ])
        wf = ComputerSystemValidationWorkflow(
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
            "Key issues: orphan requirement\n"
            "INTENDED-USE FLAGS: None detected\n"
            "TRACE-GAP FLAGS:\n- Configuration requirement URS-014 has no linked OQ test\n"
            "TEST-EVIDENCE FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = ComputerSystemValidationWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["trace_gap_flags"] == [
            "Configuration requirement URS-014 has no linked OQ test"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "INTENDED-USE FLAGS: None detected\n"
            "TRACE-GAP FLAGS:\n- URS-014 orphan requirement\n"
            "TEST-EVIDENCE FLAGS: None detected\n"
            "RECOMMENDATION: execute the missing OQ\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = ComputerSystemValidationWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.metadata["trace_gap_flags"] == ["URS-014 orphan requirement"]

    async def test_does_not_converge_when_intended_use_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "INTENDED-USE FLAGS:\n- Validation scope omits the e-signature intended use\n"
            "TRACE-GAP FLAGS: None detected\n"
            "TEST-EVIDENCE FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = ComputerSystemValidationWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["intended_use_flags"] == [
            "Validation scope omits the e-signature intended use"
        ]

    async def test_does_not_converge_when_test_evidence_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "INTENDED-USE FLAGS: None detected\n"
            "TRACE-GAP FLAGS: None detected\n"
            "TEST-EVIDENCE FLAGS:\n- URS-016 marked verified with no cited PQ evidence\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = ComputerSystemValidationWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["test_evidence_flags"] == [
            "URS-016 marked verified with no cited PQ evidence"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="INTENDED-USE FLAGS: None detected\n"
                         "TRACE-GAP FLAGS:\n- URS-014 orphan\n"
                         "TEST-EVIDENCE FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="INTENDED-USE FLAGS: None detected\n"
                         "TRACE-GAP FLAGS: None detected\n"
                         "TEST-EVIDENCE FLAGS: None detected",
            ),
        ])
        wf = ComputerSystemValidationWorkflow(
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
                critique="INTENDED-USE FLAGS: None detected\n"
                         "TRACE-GAP FLAGS: None detected\n"
                         "TEST-EVIDENCE FLAGS: None detected",
            )
        ])
        wf = ComputerSystemValidationWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert "intended_use_flags" in result.metadata
        assert "trace_gap_flags" in result.metadata
        assert "test_evidence_flags" in result.metadata
        assert "csv_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata
        checklist = result.metadata["csv_checklist"]
        assert checklist[0] == "[OWNER: Computer System Validation / Quality IT]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="INTENDED-USE FLAGS: None detected\n"
                         "TRACE-GAP FLAGS: None detected\n"
                         "TEST-EVIDENCE FLAGS: None detected",
            )
        ])
        wf = ComputerSystemValidationWorkflow(
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
            "INTENDED-USE FLAGS: None detected\n"
            "TRACE-GAP FLAGS: None detected\n"
            "TEST-EVIDENCE FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = ComputerSystemValidationWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
