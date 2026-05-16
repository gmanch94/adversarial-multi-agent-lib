"""Unit tests — ClaimsAppealReviewWorkflow."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.healthcare.workflows.claims_appeal_review import (
    ClaimsAppealRequest,
    ClaimsAppealReviewWorkflow,
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
    critique: str,
    suggestions: list[str] | None = None,
) -> ReviewResult:
    return ReviewResult(
        score=score,
        approved=approved,
        critique=critique,
        suggestions=suggestions or [],
    )


def make_request() -> ClaimsAppealRequest:
    return ClaimsAppealRequest(
        claim_id="CLM-2026-004512",
        denied_service="Cardiac MRI with contrast (CPT 75561)",
        appeal_narrative=(
            "Member appeals denial of cardiac MRI ordered by cardiologist "
            "Dr. Rivera on 2026-04-10. Echo findings non-diagnostic for "
            "suspected cardiac sarcoidosis; MRI required per ACC/AHA guideline "
            "2023 section 4.3."
        ),
        clinical_evidence=(
            "Echocardiogram 2026-03-15: biventricular dysfunction, EF 40%, "
            "non-diagnostic for infiltrative cardiomyopathy. "
            "Holter monitor: runs of NSVT. "
            "ACC/AHA 2023 guideline section 4.3: cardiac MRI indicated for "
            "suspected infiltrative cardiomyopathy when echo is non-diagnostic."
        ),
        coverage_policy=(
            "Acme Health Plan Imaging Policy IMG-007 effective 2026-01-01: "
            "Cardiac MRI covered when echo is non-diagnostic and ordering "
            "physician documents clinical indication per ACC/AHA guideline."
        ),
        original_review_summary=(
            "Claim denied 2026-04-18: reviewer determined cardiac MRI not "
            "medically necessary; echo deemed sufficient for diagnosis. "
            "InterQual 2025 cardiology criteria applied."
        ),
        treating_physician_statement=(
            "Dr. Rivera attests: echo non-diagnostic for sarcoidosis; "
            "cardiac MRI essential for diagnosis and treatment planning. "
            "Peer-reviewed evidence and ACC/AHA guideline support use."
        ),
    )


@pytest.mark.asyncio
class TestRequestDataclass:
    async def test_to_prompt_text_includes_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        assert "CLM-2026-004512" in text
        assert "Cardiac MRI" in text
        assert "appeal narrative" in text.lower()
        assert "clinical evidence" in text.lower()
        assert "coverage policy" in text.lower()
        assert "original review summary" in text.lower()
        assert "treating physician statement" in text.lower()

    async def test_field_cap_applied(self) -> None:
        long = "x" * 2000
        req = ClaimsAppealRequest(
            claim_id=long,
            denied_service=long,
            appeal_narrative=long,
            clinical_evidence=long,
            coverage_policy=long,
            original_review_summary=long,
            treating_physician_statement=long,
        )
        text = req.to_prompt_text()
        for line in text.splitlines():
            value = line.split(": ", 1)[1] if ": " in line else line
            assert len(value) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_on_first_round_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Appeal review\nRecommend overturn."])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique=(
                    "EVIDENCE FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "PROCEDURE FLAGS: None detected"
                ),
            )
        ])
        wf = ClaimsAppealReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_with_evidence_flag(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2", "draft 3"])
        critique_with_flag = (
            "EVIDENCE FLAGS:\n"
            "  - Clinical evidence does not cite specific guideline section\n"
            "COVERAGE FLAGS: None detected\n"
            "PROCEDURE FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(
                8.5, approved=True,
                critique=critique_with_flag,
            ),
            make_review(
                8.5, approved=True,
                critique=critique_with_flag,
            ),
            make_review(
                8.5, approved=True,
                critique=critique_with_flag,
            ),
        ])
        wf = ClaimsAppealReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique=(
                    "EVIDENCE FLAGS:\n"
                    "  - Missing lab reference range\n"
                    "COVERAGE FLAGS: None detected\n"
                    "PROCEDURE FLAGS: None detected"
                ),
            ),
            make_review(
                9.0, approved=True,
                critique=(
                    "EVIDENCE FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "PROCEDURE FLAGS: None detected"
                ),
            ),
        ])
        wf = ClaimsAppealReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2

    async def test_does_not_converge_below_score_threshold(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2", "draft 3"])
        reviewer = FakeReviewer([
            make_review(
                6.0, approved=False,
                critique=(
                    "EVIDENCE FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "PROCEDURE FLAGS: None detected"
                ),
            ),
            make_review(
                6.0, approved=False,
                critique=(
                    "EVIDENCE FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "PROCEDURE FLAGS: None detected"
                ),
            ),
            make_review(
                6.0, approved=False,
                critique=(
                    "EVIDENCE FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "PROCEDURE FLAGS: None detected"
                ),
            ),
        ])
        wf = ClaimsAppealReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique=(
                    "EVIDENCE FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "PROCEDURE FLAGS: None detected"
                ),
            )
        ])
        wf = ClaimsAppealReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert "evidence_flags" in result.metadata
        assert "coverage_flags" in result.metadata
        assert "procedure_flags" in result.metadata
        assert "appeal_checklist" in result.metadata
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
                    "EVIDENCE FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "PROCEDURE FLAGS: None detected"
                ),
            )
        ])
        wf = ClaimsAppealReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
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
            "EVIDENCE FLAGS: None detected\n"
            "COVERAGE FLAGS: None detected\n"
            "PROCEDURE FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = ClaimsAppealReviewWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
