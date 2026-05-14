"""Unit tests for CyberUnderwritingWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.pc.workflows.cyber_underwriting import (
    CyberUnderwritingRequest,
    CyberUnderwritingWorkflow,
    _DISCLAIMER,
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
    score: float, *, approved: bool, critique: str = "",
    suggestions: list[str] | None = None,
) -> ReviewResult:
    return ReviewResult(
        score=score, critique=critique,
        suggestions=suggestions or [], approved=approved,
    )


def make_request(**kwargs: Any) -> CyberUnderwritingRequest:
    defaults: dict[str, Any] = dict(
        applicant_summary="Healthcare SaaS; $34M ARR; 198 staff; 11.2M patient PHI in AWS.",
        control_attestations="MFA admin/portal; CrowdStrike EDR 100%; S3 versioned backups; SOC2 vendor reviews.",
        control_evidence="BitSight 720/950; 2024 credential-stuffing incident, no exfil; no S3 Object Lock; no IR retainer.",
        requested_coverage="Aggregate $10M; ransomware $7.5M; BI $5M; privacy $5M; SE $500k.",
        proposed_terms="Premium $148k; retention $100k; ransomware reduced to $5M; LMA5564 war exclusion.",
        aggregation_context="Healthcare-SaaS 18% LOB cap; AWS 41% (cap 50%); CrowdStrike 67%.",
    )
    defaults.update(kwargs)
    return CyberUnderwritingRequest(**defaults)


def make_workflow(
    config: Config, tmp_path: Path,
    executor: FakeExecutor, reviewer: FakeReviewer,
) -> CyberUnderwritingWorkflow:
    return CyberUnderwritingWorkflow(
        config=config, executor=executor, reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Applicant Summary
Healthcare SaaS; HIPAA PHI scale 11.2M; AWS dual-region; $34M ARR.

## Control Maturity Assessment
MFA full; EDR 100%; backup immutable via policy only (S3 Object Lock GAP); no IR retainer (GAP).

## Proposed Bind Terms
Aggregate $10M; ransomware $5M (reduced for Object Lock gap); BI $5M; privacy $5M; LMA5564 war.

## Sub-Limit Justification
Ransomware sub-limit tied to backup-immutability gap; privacy $5M scaled to PHI record volume.

## Portfolio Aggregation Check
Healthcare-SaaS 20% post-bind (cap 25%); AWS 41% (cap 50%); CrowdStrike concentration NOTED.

## IR Retainer & Vendor Panel
Condition precedent: panel DFIR retainer within 60 days; HIPAA breach coach pre-approved.

## Evidence Gaps
2024 incident root-cause report not on file; should be a CP for credential-stuffing mitigations.

## Claims
[Source: control_evidence] S3 Object Lock is not configured on backup buckets.
[Source: aggregation_context] CrowdStrike concentration in the portfolio is 67%.
[Source: applicant_summary] PHI volume is approximately 11.2 million unique patient records.
"""


_CLEAN_CRITIQUE = """\
Sound bind with stated conditions.

Overall score: 8.0/10
Key issues:
- 2024 incident RCA should be CP.

CONTROL-GAP FLAGS: None detected
SUB-LIMIT FLAGS: None detected
AGGREGATION FLAGS: None detected
"""


class TestCyberConvergence:
    @pytest.mark.asyncio
    async def test_converges_on_clean_critique(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True

    @pytest.mark.asyncio
    async def test_does_not_converge_when_control_gap_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: backup immutability gap\n"
            "CONTROL-GAP FLAGS:\n- S3 Object Lock not configured — ransomware sub-limit must drop further\n"
            "SUB-LIMIT FLAGS: None detected\n"
            "AGGREGATION FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Object Lock" in f for f in result.metadata["control_gap_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_sub_limit_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: ransomware miscalibrated\n"
            "CONTROL-GAP FLAGS: None detected\n"
            "SUB-LIMIT FLAGS:\n- Ransomware $5M still too high vs Object Lock gap; recommend $3M\n"
            "AGGREGATION FLAGS: None detected"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Ransomware" in f for f in result.metadata["sub_limit_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_aggregation_flags_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 6.5/10\nKey issues: vendor concentration\n"
            "CONTROL-GAP FLAGS: None detected\n"
            "SUB-LIMIT FLAGS: None detected\n"
            "AGGREGATION FLAGS:\n- CrowdStrike 67% concentration creates systemic-event correlation\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(6.5, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("CrowdStrike" in f for f in result.metadata["aggregation_flags"])


class TestCyberOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_claims_registered_into_ledger(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.0, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 3


class TestCyberUnderwritingRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        for fragment in [
            "Applicant summary:",
            "Control attestations:",
            "Control evidence:",
            "Requested coverage:",
            "Proposed terms:",
            "Aggregation context:",
        ]:
            assert fragment in text
