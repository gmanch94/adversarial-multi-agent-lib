"""Unit tests for PriorAuthorizationReviewWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.healthcare.workflows.prior_authorization_review import (
    PriorAuthorizationReviewWorkflow,
    PriorAuthRequest,
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


def make_request(**kwargs: Any) -> PriorAuthRequest:
    defaults: dict[str, Any] = dict(
        member_id="MEM-2026-004881",
        requested_service=(
            "Tafamidis (Vyndaqel) 61 mg daily for transthyretin amyloid "
            "cardiomyopathy (ATTR-CM) — 90-day supply, specialty pharmacy"
        ),
        clinical_rationale=(
            "Patient has confirmed wild-type ATTR-CM on technetium pyrophosphate "
            "scintigraphy (grade 3 uptake) and cardiac MRI. LVEF 45%; NYHA class "
            "II–III heart failure. Tafamidis is the only FDA-approved disease-"
            "modifying therapy for ATTR-CM (ATTR-ACT trial, NEJM 2018). "
            "Cardiologist attests medical necessity."
        ),
        diagnosis_codes=(
            "I43 (Cardiomyopathy in diseases classified elsewhere), "
            "E85.81 (Light chain (AL) amyloidosis), "
            "I50.9 (Heart failure, unspecified)"
        ),
        clinical_guidelines=(
            "ACC/AHA Heart Failure Guideline 2022 Section 7.5: tafamidis "
            "recommended (Class I, LOE B-R) for ATTR-CM patients with NYHA "
            "class I–III symptoms. InterQual 2025 PA Criteria: requires "
            "confirmatory nuclear scan or biopsy + NYHA II–III."
        ),
        member_history=(
            "65yo male, commercial plan (Acme PPO). No prior tafamidis claims. "
            "Active prescriptions: furosemide 40 mg, carvedilol 12.5 mg, "
            "spironolactone 25 mg. No prior hospitalizations for CHF in past 12 mo. "
            "Genetic testing negative for hereditary TTR variants (Val122Ile, Val30Met)."
        ),
        alternatives_tried=(
            "Patient trialed standard heart failure guideline-directed medical "
            "therapy (GDMT) for 18 months: ACEi/ARB, beta-blocker, MRA. "
            "Symptoms persisted at NYHA class II–III despite optimized GDMT. "
            "Diflunisal not appropriate — patient has CKD stage 2 (eGFR 62)."
        ),
    )
    defaults.update(kwargs)
    return PriorAuthRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        request = make_request()
        text = request.to_prompt_text()
        assert "Member ID:" in text
        assert "Requested service:" in text
        assert "Clinical rationale:" in text
        assert "Diagnosis codes:" in text
        assert "Clinical guidelines:" in text
        assert "Member history:" in text
        assert "Alternatives tried:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        request = make_request(clinical_rationale=oversized)
        text = request.to_prompt_text()
        rationale_section = text.split("Clinical rationale:")[1].split("\n")[0]
        assert len(rationale_section.strip()) <= _MAX_FIELD_CHARS + 5  # +5 for whitespace


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_on_first_round_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Prior auth review\nApprove tafamidis."])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique=(
                    "MEDICAL-NECESSITY FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "DOCUMENTATION FLAGS: None detected"
                ),
            )
        ])
        wf = PriorAuthorizationReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_with_medical_necessity_flag(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2", "draft 3"])
        critique_with_flag = (
            "MEDICAL-NECESSITY FLAGS:\n"
            "  - Medical necessity cited from general practice, not from "
            "InterQual 2025 criteria\n"
            "COVERAGE FLAGS: None detected\n"
            "DOCUMENTATION FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(9.0, approved=True, critique=critique_with_flag),
            make_review(9.0, approved=True, critique=critique_with_flag),
            make_review(9.0, approved=True, critique=critique_with_flag),
        ])
        wf = PriorAuthorizationReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
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
                    "MEDICAL-NECESSITY FLAGS:\n"
                    "  - Necessity claim not grounded in clinical guideline section\n"
                    "COVERAGE FLAGS: None detected\n"
                    "DOCUMENTATION FLAGS: None detected"
                ),
            ),
            make_review(
                9.0, approved=True,
                critique=(
                    "MEDICAL-NECESSITY FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "DOCUMENTATION FLAGS: None detected"
                ),
            ),
        ])
        wf = PriorAuthorizationReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2


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
                    "MEDICAL-NECESSITY FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "DOCUMENTATION FLAGS: None detected"
                ),
            )
        ])
        wf = PriorAuthorizationReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert "medical_necessity_flags" in result.metadata
        assert "coverage_flags" in result.metadata
        assert "documentation_flags" in result.metadata
        assert "prior_auth_checklist" in result.metadata
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
                    "MEDICAL-NECESSITY FLAGS: None detected\n"
                    "COVERAGE FLAGS: None detected\n"
                    "DOCUMENTATION FLAGS: None detected"
                ),
            )
        ])
        wf = PriorAuthorizationReviewWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
        assert "ADVISORY" in _DISCLAIMER.upper()
