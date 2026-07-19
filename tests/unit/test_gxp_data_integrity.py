"""Unit tests for GxPDataIntegrityWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.gxp_data_integrity import (
    GxPDataIntegrityRequest,
    GxPDataIntegrityWorkflow,
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


def make_request(**kwargs: Any) -> GxPDataIntegrityRequest:
    defaults: dict[str, Any] = dict(
        system_description="Chromatography data system on a QC lab bench "
                           "supporting GMP release testing of finished product.",
        record_type="Hybrid: electronic chromatograms with paper printouts "
                    "countersigned by the analyst.",
        audit_trail_summary="Audit trail is enabled and tamper-evident but is "
                           "not part of the routine review-by-exception checklist.",
        access_control_summary="Named analyst logins, except one shared login "
                             "retained for a legacy instrument.",
        data_lifecycle_summary="Create -> process -> review -> report -> "
                             "archive on validated storage with 10-year retention.",
        alcoa_assessment="Caller asserts all ALCOA+ attributes met; "
                        "contemporaneous recording not evidenced for the legacy instrument.",
        deviations_investigations="One prior integration-parameter deviation; "
                                "CAPA closed.",
        review_by_exception_summary="Review by exception covers integration but "
                                  "not audit-trail entries.",
    )
    defaults.update(kwargs)
    return GxPDataIntegrityRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        request = make_request()
        text = request.to_prompt_text()
        assert "System description:" in text
        assert "Record type:" in text
        assert "Audit trail summary:" in text
        assert "Access control summary:" in text
        assert "Data lifecycle summary:" in text
        assert "ALCOA assessment:" in text
        assert "Deviations and investigations:" in text
        assert "Review by exception summary:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        request = make_request(audit_trail_summary=oversized)
        text = request.to_prompt_text()
        section = text.split("Audit trail summary:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## ALCOA+ attribute assessment\nAll attributes met"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="ALCOA FLAGS: None detected\n"
                         "AUDIT-TRAIL FLAGS: None detected\n"
                         "ATTRIBUTION FLAGS: None detected",
            )
        ])
        wf = GxPDataIntegrityWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_alcoa_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: contemporaneous recording\n"
            "ALCOA FLAGS:\n"
            "- Contemporaneous recording not demonstrated for the legacy instrument\n"
            "AUDIT-TRAIL FLAGS: None detected\n"
            "ATTRIBUTION FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = GxPDataIntegrityWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["alcoa_flags"] == [
            "Contemporaneous recording not demonstrated for the legacy instrument"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "ALCOA FLAGS:\n- Legacy instrument lacks contemporaneous recording\n"
            "AUDIT-TRAIL FLAGS: None detected\n"
            "ATTRIBUTION FLAGS: None detected\n"
            "RECOMMENDATION: retire the shared login\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = GxPDataIntegrityWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.metadata["alcoa_flags"] == [
            "Legacy instrument lacks contemporaneous recording"
        ]

    async def test_does_not_converge_when_audit_trail_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "ALCOA FLAGS: None detected\n"
            "AUDIT-TRAIL FLAGS:\n- Audit trail is not part of the routine review\n"
            "ATTRIBUTION FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = GxPDataIntegrityWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["audit_trail_flags"] == [
            "Audit trail is not part of the routine review"
        ]

    async def test_does_not_converge_when_attribution_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "ALCOA FLAGS: None detected\n"
            "AUDIT-TRAIL FLAGS: None detected\n"
            "ATTRIBUTION FLAGS:\n- Shared legacy login breaks unique attribution\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = GxPDataIntegrityWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["attribution_flags"] == [
            "Shared legacy login breaks unique attribution"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="ALCOA FLAGS:\n- Legacy instrument gap\n"
                         "AUDIT-TRAIL FLAGS: None detected\n"
                         "ATTRIBUTION FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="ALCOA FLAGS: None detected\n"
                         "AUDIT-TRAIL FLAGS: None detected\n"
                         "ATTRIBUTION FLAGS: None detected",
            ),
        ])
        wf = GxPDataIntegrityWorkflow(executor=executor, reviewer=reviewer, config=config)
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
                critique="ALCOA FLAGS: None detected\n"
                         "AUDIT-TRAIL FLAGS: None detected\n"
                         "ATTRIBUTION FLAGS: None detected",
            )
        ])
        wf = GxPDataIntegrityWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert "alcoa_flags" in result.metadata
        assert "audit_trail_flags" in result.metadata
        assert "attribution_flags" in result.metadata
        assert "gxp_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata
        checklist = result.metadata["gxp_checklist"]
        assert checklist[0] == "[OWNER: Quality Assurance / Data Integrity Lead]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="ALCOA FLAGS: None detected\n"
                         "AUDIT-TRAIL FLAGS: None detected\n"
                         "ATTRIBUTION FLAGS: None detected",
            )
        ])
        wf = GxPDataIntegrityWorkflow(executor=executor, reviewer=reviewer, config=config)
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
            "ALCOA FLAGS: None detected\n"
            "AUDIT-TRAIL FLAGS: None detected\n"
            "ATTRIBUTION FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = GxPDataIntegrityWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
