"""Unit tests for DiagnosisCodeAuditWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.healthcare.workflows.diagnosis_code_audit import (
    DiagnosisCodeAuditWorkflow,
    DiagnosisCodeAuditRequest,
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


def make_request(**kwargs: Any) -> DiagnosisCodeAuditRequest:
    defaults: dict[str, Any] = dict(
        encounter_summary="65yo M admitted with NSTEMI, cath shows 90% LAD lesion, "
                          "PCI with DES placed. PMH HTN, DM2, CKD3. LOS 3 days.",
        proposed_codes="I21.4 (NSTEMI); E11.22 (DM2 w/CKD); I12.9 (HTN w/CKD); "
                       "N18.30 (CKD3); 92928 (PCI single vessel w/DES)",
        provider_specialty="cardiology",
        payer_guidelines="Medicare LCD L33797; AHA Coding Clinic Q2 2025",
        previous_audits="Prior audit flagged undercoding of CKD stage specificity",
        clinical_context="Inpatient admission; PCI procedure; 3-day LOS",
    )
    defaults.update(kwargs)
    return DiagnosisCodeAuditRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        request = make_request()
        text = request.to_prompt_text()
        assert "Encounter summary:" in text
        assert "Proposed codes:" in text
        assert "Provider specialty:" in text
        assert "Payer guidelines:" in text
        assert "Previous audits:" in text
        assert "Clinical context:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        # L-PC-3 invariant — oversized field is sliced to _MAX_FIELD_CHARS
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        request = make_request(encounter_summary=oversized)
        text = request.to_prompt_text()
        # The truncated field appears at most _MAX_FIELD_CHARS x's after the label
        encounter_section = text.split("Encounter summary:")[1].split("\n")[0]
        assert len(encounter_section.strip()) <= _MAX_FIELD_CHARS + 5  # +5 for whitespace


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_on_first_round_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Codes\nI21.4 — accurate"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="ACCURACY FLAGS: None detected\n"
                        "COMPLIANCE FLAGS: None detected\n"
                        "SPECIFICITY FLAGS: None detected",
            )
        ])
        wf = DiagnosisCodeAuditWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_with_accuracy_flag(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2", "draft 3"])
        critique_with_flag = (
            "ACCURACY FLAGS:\n"
            "  - I12.9 should be I12.0 given CKD3 + HTN per AHA Coding Clinic\n"
            "COMPLIANCE FLAGS: None detected\n"
            "SPECIFICITY FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(9.0, approved=True, critique=critique_with_flag),
            make_review(9.0, approved=True, critique=critique_with_flag),
            make_review(9.0, approved=True, critique=critique_with_flag),
        ])
        wf = DiagnosisCodeAuditWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3  # max_review_rounds

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="ACCURACY FLAGS:\n  - I12.9 specificity\n"
                         "COMPLIANCE FLAGS: None detected\n"
                         "SPECIFICITY FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="ACCURACY FLAGS: None detected\n"
                         "COMPLIANCE FLAGS: None detected\n"
                         "SPECIFICITY FLAGS: None detected",
            ),
        ])
        wf = DiagnosisCodeAuditWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="ACCURACY FLAGS: None detected\n"
                         "COMPLIANCE FLAGS: None detected\n"
                         "SPECIFICITY FLAGS: None detected",
            )
        ])
        wf = DiagnosisCodeAuditWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert "accuracy_flags" in result.metadata
        assert "compliance_flags" in result.metadata
        assert "specificity_flags" in result.metadata
        assert "audit_checklist" in result.metadata
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
                critique="ACCURACY FLAGS: None detected\n"
                         "COMPLIANCE FLAGS: None detected\n"
                         "SPECIFICITY FLAGS: None detected",
            )
        ])
        wf = DiagnosisCodeAuditWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
        assert "ADVISORY" in _DISCLAIMER.upper()
