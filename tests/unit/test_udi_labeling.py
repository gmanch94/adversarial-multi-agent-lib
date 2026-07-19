"""Unit tests for UDILabelingWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.udi_labeling import (
    UDILabelingRequest,
    UDILabelingWorkflow,
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


def make_request(**kwargs: Any) -> UDILabelingRequest:
    defaults: dict[str, Any] = dict(
        device_identifier="A reusable surgical instrument (rigid endoscope "
                        "class), single model.",
        di_pi_structure="DI plus PI lot and serial; DI issued under a GS1 GTIN.",
        issuing_agency="GS1.",
        gudid_record_summary="GUDID record with device count, sterilization, and "
                          "brand-name attribute submitted.",
        label_artwork_summary="Case label carries human-readable UDI plus a "
                           "linear barcode; direct-mark on the instrument body.",
        packaging_hierarchy="Each instrument -> single case; no inner pack tier.",
        direct_marking_status="Direct-mark present; DI on the mark under review "
                          "against the label DI.",
        regional_scope="United States (GUDID) and European Union (EUDAMED).",
    )
    defaults.update(kwargs)
    return UDILabelingRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        assert "Device identifier:" in text
        assert "DI/PI structure:" in text
        assert "Issuing agency:" in text
        assert "GUDID record summary:" in text
        assert "Label artwork summary:" in text
        assert "Packaging hierarchy:" in text
        assert "Direct marking status:" in text
        assert "Regional scope:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(gudid_record_summary=oversized).to_prompt_text()
        section = text.split("GUDID record summary:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Identifier structure\nValid"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="IDENTIFIER FLAGS: None detected\n"
                         "GUDID-CONSISTENCY FLAGS: None detected\n"
                         "PACKAGING-TIER FLAGS: None detected",
            )
        ])
        wf = UDILabelingWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_gudid_consistency_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: database mismatch\n"
            "IDENTIFIER FLAGS: None detected\n"
            "GUDID-CONSISTENCY FLAGS:\n"
            "- GUDID brand attribute does not match current label artwork\n"
            "PACKAGING-TIER FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = UDILabelingWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["gudid_consistency_flags"] == [
            "GUDID brand attribute does not match current label artwork"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "IDENTIFIER FLAGS: None detected\n"
            "GUDID-CONSISTENCY FLAGS:\n- Stale GUDID attribute vs label\n"
            "PACKAGING-TIER FLAGS: None detected\n"
            "RECOMMENDATION: update the GUDID record\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = UDILabelingWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.metadata["gudid_consistency_flags"] == ["Stale GUDID attribute vs label"]

    async def test_does_not_converge_when_identifier_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "IDENTIFIER FLAGS:\n- DI/PI omits the required lot production identifier\n"
            "GUDID-CONSISTENCY FLAGS: None detected\n"
            "PACKAGING-TIER FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = UDILabelingWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["identifier_flags"] == [
            "DI/PI omits the required lot production identifier"
        ]

    async def test_does_not_converge_when_packaging_tier_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "IDENTIFIER FLAGS: None detected\n"
            "GUDID-CONSISTENCY FLAGS: None detected\n"
            "PACKAGING-TIER FLAGS:\n- Direct-mark DI does not match the case label DI\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = UDILabelingWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["packaging_tier_flags"] == [
            "Direct-mark DI does not match the case label DI"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="IDENTIFIER FLAGS: None detected\n"
                         "GUDID-CONSISTENCY FLAGS:\n- Stale attribute\n"
                         "PACKAGING-TIER FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="IDENTIFIER FLAGS: None detected\n"
                         "GUDID-CONSISTENCY FLAGS: None detected\n"
                         "PACKAGING-TIER FLAGS: None detected",
            ),
        ])
        wf = UDILabelingWorkflow(executor=executor, reviewer=reviewer, config=config)
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
                critique="IDENTIFIER FLAGS: None detected\n"
                         "GUDID-CONSISTENCY FLAGS: None detected\n"
                         "PACKAGING-TIER FLAGS: None detected",
            )
        ])
        wf = UDILabelingWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert "identifier_flags" in result.metadata
        assert "gudid_consistency_flags" in result.metadata
        assert "packaging_tier_flags" in result.metadata
        assert "udi_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata
        checklist = result.metadata["udi_checklist"]
        assert checklist[0] == "[OWNER: Regulatory Labeling / UDI Coordinator]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="IDENTIFIER FLAGS: None detected\n"
                         "GUDID-CONSISTENCY FLAGS: None detected\n"
                         "PACKAGING-TIER FLAGS: None detected",
            )
        ])
        wf = UDILabelingWorkflow(executor=executor, reviewer=reviewer, config=config)
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
            "IDENTIFIER FLAGS: None detected\n"
            "GUDID-CONSISTENCY FLAGS: None detected\n"
            "PACKAGING-TIER FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = UDILabelingWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
