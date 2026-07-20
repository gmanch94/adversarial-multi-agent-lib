"""Unit tests for PostMarketClinicalFollowupWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.post_market_clinical_followup import (
    PMCFRequest,
    PostMarketClinicalFollowupWorkflow,
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


def make_request(**kwargs: Any) -> PMCFRequest:
    defaults: dict[str, Any] = dict(
        device_description="A total hip replacement implant (metal-on-polyethylene) "
                           "indicated for degenerative joint disease in adults.",
        clinical_evidence_baseline="Pre-market pivotal study at 2 years plus "
                                   "literature on the bearing couple.",
        pmcf_objectives="Confirm long-term (10-year) survivorship and wear "
                        "performance in routine use.",
        pmcf_methods="Complaint-data trending; a planned literature review.",
        residual_risks="Long-term polyethylene wear leading to osteolysis and "
                      "revision; rare adverse local tissue reaction.",
        benefit_risk_baseline="Favorable at 2 years; long-term wear risk carried "
                             "as residual.",
        data_collected_summary="18 months of complaint data; no registry linkage.",
        pms_linkage="Complaint trends summarized in the annual PMS report.",
    )
    defaults.update(kwargs)
    return PMCFRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Device description:",
            "Clinical evidence baseline:",
            "PMCF objectives:",
            "PMCF methods:",
            "Residual risks:",
            "Benefit-risk baseline:",
            "Data collected summary:",
            "PMS linkage:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(pmcf_methods=oversized).to_prompt_text()
        section = text.split("PMCF methods:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Evidence sufficiency\nAll claims supported"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="EVIDENCE-GAP FLAGS: None detected\n"
                         "RESIDUAL-RISK FLAGS: None detected\n"
                         "PMCF-ADEQUACY FLAGS: None detected",
            )
        ])
        wf = PostMarketClinicalFollowupWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_pmcf_adequacy_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: method inadequate\n"
            "EVIDENCE-GAP FLAGS: None detected\n"
            "RESIDUAL-RISK FLAGS: None detected\n"
            "PMCF-ADEQUACY FLAGS:\n- Complaint data alone cannot detect the long-term wear revision-rate risk\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = PostMarketClinicalFollowupWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["pmcf_adequacy_flags"] == [
            "Complaint data alone cannot detect the long-term wear revision-rate risk"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "EVIDENCE-GAP FLAGS:\n- 10-year survivorship claim lacks post-market evidence\n"
            "RECOMMENDATION: enroll in a registry\n"
            "RESIDUAL-RISK FLAGS: None detected\n"
            "PMCF-ADEQUACY FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = PostMarketClinicalFollowupWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.metadata["evidence_gap_flags"] == [
            "10-year survivorship claim lacks post-market evidence"
        ]

    async def test_does_not_converge_when_residual_risk_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "EVIDENCE-GAP FLAGS: None detected\n"
            "RESIDUAL-RISK FLAGS:\n- Adverse local tissue reaction risk has no covering PMCF activity\n"
            "PMCF-ADEQUACY FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = PostMarketClinicalFollowupWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["residual_risk_flags"] == [
            "Adverse local tissue reaction risk has no covering PMCF activity"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="EVIDENCE-GAP FLAGS:\n- 10-year claim unevidenced\n"
                         "RESIDUAL-RISK FLAGS: None detected\n"
                         "PMCF-ADEQUACY FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="EVIDENCE-GAP FLAGS: None detected\n"
                         "RESIDUAL-RISK FLAGS: None detected\n"
                         "PMCF-ADEQUACY FLAGS: None detected",
            ),
        ])
        wf = PostMarketClinicalFollowupWorkflow(
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
                critique="EVIDENCE-GAP FLAGS: None detected\n"
                         "RESIDUAL-RISK FLAGS: None detected\n"
                         "PMCF-ADEQUACY FLAGS: None detected",
            )
        ])
        wf = PostMarketClinicalFollowupWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        for key in (
            "device_description",
            "evidence_gap_flags",
            "residual_risk_flags",
            "pmcf_adequacy_flags",
            "pmcf_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["pmcf_checklist"][0] == (
            "[OWNER: Clinical Affairs / Post-Market Surveillance]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="EVIDENCE-GAP FLAGS: None detected\n"
                         "RESIDUAL-RISK FLAGS: None detected\n"
                         "PMCF-ADEQUACY FLAGS: None detected",
            )
        ])
        wf = PostMarketClinicalFollowupWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
        assert "ADVISORY" in _DISCLAIMER.upper()


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        clean_critique = (
            "EVIDENCE-GAP FLAGS: None detected\n"
            "RESIDUAL-RISK FLAGS: None detected\n"
            "PMCF-ADEQUACY FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = PostMarketClinicalFollowupWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
