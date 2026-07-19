"""Unit tests for CMOQualificationWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.cmo_qualification import (
    CMOQualificationRequest,
    CMOQualificationWorkflow,
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


def make_request(**kwargs: Any) -> CMOQualificationRequest:
    defaults: dict[str, Any] = dict(
        supplier_description="A sterile fill-finish CDMO proposed for a new "
                           "commercial aseptic vial product.",
        audit_findings_summary="Last audit: two major observations "
                            "(environmental monitoring, gowning qualification).",
        gmp_history="One prior regulatory inspection with voluntary corrections; "
                 "no warning letter.",
        data_integrity_posture="Reviewed audit trails; segregation of duties in "
                            "place; no shared logins reported.",
        capacity_assessment="Declares two aseptic lines; utilization already high "
                          "on committed volumes.",
        quality_agreement_status="Draft quality agreement; not yet executed.",
        capa_status="Open CAPA on environmental monitoring; gowning CAPA closed.",
        technical_transfer_readiness="Process validation protocol drafted; not yet "
                                  "executed at the CDMO.",
    )
    defaults.update(kwargs)
    return CMOQualificationRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        assert "Supplier description:" in text
        assert "Audit findings summary:" in text
        assert "GMP history:" in text
        assert "Data integrity posture:" in text
        assert "Capacity assessment:" in text
        assert "Quality agreement status:" in text
        assert "CAPA status:" in text
        assert "Technical transfer readiness:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(audit_findings_summary=oversized).to_prompt_text()
        section = text.split("Audit findings summary:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## GMP compliance\nRemediated"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="GMP-GAP FLAGS: None detected\n"
                         "DATA-INTEGRITY FLAGS: None detected\n"
                         "CAPACITY FLAGS: None detected",
            )
        ])
        wf = CMOQualificationWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_gmp_gap_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: open CAPA\n"
            "GMP-GAP FLAGS:\n"
            "- Open CAPA on environmental monitoring not remediated before qualification\n"
            "DATA-INTEGRITY FLAGS: None detected\n"
            "CAPACITY FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = CMOQualificationWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["gmp_gap_flags"] == [
            "Open CAPA on environmental monitoring not remediated before qualification"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "GMP-GAP FLAGS:\n- Environmental monitoring CAPA still open\n"
            "DATA-INTEGRITY FLAGS: None detected\n"
            "CAPACITY FLAGS: None detected\n"
            "RECOMMENDATION: re-audit after CAPA closure\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = CMOQualificationWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.metadata["gmp_gap_flags"] == [
            "Environmental monitoring CAPA still open"
        ]

    async def test_does_not_converge_when_data_integrity_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "GMP-GAP FLAGS: None detected\n"
            "DATA-INTEGRITY FLAGS:\n- QC balance audit trail not reviewed\n"
            "CAPACITY FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = CMOQualificationWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["data_integrity_flags"] == [
            "QC balance audit trail not reviewed"
        ]

    async def test_does_not_converge_when_capacity_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "GMP-GAP FLAGS: None detected\n"
            "DATA-INTEGRITY FLAGS: None detected\n"
            "CAPACITY FLAGS:\n- Declared line capacity insufficient for the committed volume\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = CMOQualificationWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["capacity_flags"] == [
            "Declared line capacity insufficient for the committed volume"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="GMP-GAP FLAGS:\n- Open CAPA\n"
                         "DATA-INTEGRITY FLAGS: None detected\n"
                         "CAPACITY FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="GMP-GAP FLAGS: None detected\n"
                         "DATA-INTEGRITY FLAGS: None detected\n"
                         "CAPACITY FLAGS: None detected",
            ),
        ])
        wf = CMOQualificationWorkflow(executor=executor, reviewer=reviewer, config=config)
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
                critique="GMP-GAP FLAGS: None detected\n"
                         "DATA-INTEGRITY FLAGS: None detected\n"
                         "CAPACITY FLAGS: None detected",
            )
        ])
        wf = CMOQualificationWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert "gmp_gap_flags" in result.metadata
        assert "data_integrity_flags" in result.metadata
        assert "capacity_flags" in result.metadata
        assert "cmo_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata
        checklist = result.metadata["cmo_checklist"]
        assert checklist[0] == "[OWNER: Supplier Quality / External Manufacturing]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="GMP-GAP FLAGS: None detected\n"
                         "DATA-INTEGRITY FLAGS: None detected\n"
                         "CAPACITY FLAGS: None detected",
            )
        ])
        wf = CMOQualificationWorkflow(executor=executor, reviewer=reviewer, config=config)
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
            "GMP-GAP FLAGS: None detected\n"
            "DATA-INTEGRITY FLAGS: None detected\n"
            "CAPACITY FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = CMOQualificationWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
