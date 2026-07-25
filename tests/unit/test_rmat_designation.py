"""Unit tests for RMATDesignationWorkflow (Lifesciences CGT · no-veto) — no live API.

Triple-flag no-veto (D-LIFESCI-8). Mirrors the no-veto shape.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.rmat_designation import (
    RMATDesignationWorkflow,
    RMATRequest,
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
        score_threshold=8.0,
    )
    defaults.update(kwargs)
    return Config(**defaults)


def make_review(score: float, *, approved: bool, critique: str = "") -> ReviewResult:
    return ReviewResult(score=score, critique=critique, suggestions=[], approved=approved)


def make_request(**kwargs: Any) -> RMATRequest:
    defaults: dict[str, Any] = dict(
        product_description=(
            "An autologous gene-modified cell therapy for a rare inherited disorder."
        ),
        serious_condition_rationale=(
            "The disorder is progressive and life-limiting with a median survival "
            "reduction versus the general population."
        ),
        preliminary_clinical_evidence=(
            "A single-arm study of 18 patients showed a durable response on a "
            "validated clinical endpoint at 12 months versus a natural-history "
            "control."
        ),
        unmet_medical_need=(
            "No disease-modifying therapy is currently approved; only supportive "
            "care is available."
        ),
        intent_to_address_unmet_need=(
            "The therapy targets the underlying genetic defect to modify disease "
            "progression."
        ),
        available_therapy_landscape=(
            "Supportive care and symptomatic management only; no approved "
            "disease-modifying option."
        ),
        prior_fda_interactions=(
            "A pre-IND meeting was held; the agency acknowledged the natural-history "
            "control approach."
        ),
    )
    defaults.update(kwargs)
    return RMATRequest(**defaults)


def clean_critique() -> str:
    return (
        "Evidence credible; condition serious; unmet need supported.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm the natural-history control comparability\n"
        "EVIDENCE-STRETCH FLAGS: None detected\n"
        "SERIOUS-CONDITION FLAGS: None detected\n"
        "UNMET-NEED FLAGS: None detected\n"
    )


_GOOD_OUTPUT = """\
## Regenerative-medicine-therapy qualification
An autologous gene-modified cell therapy qualifies as a regenerative-medicine
therapy.

## Serious or life-threatening condition
The progressive, life-limiting disorder meets the serious bar.

## Preliminary clinical evidence
A single-arm study of 18 patients with a durable 12-month response vs a
natural-history control credibly indicates potential.

## Unmet medical need
No approved disease-modifying therapy exists.

## Eligibility conclusion
The product appears eligible for RMAT designation.

## Claims
[Source: preliminary_clinical_evidence] 18-patient single-arm durable response at 12 months.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Serious-condition rationale:",
            "Preliminary clinical evidence:",
            "Unmet medical need:",
            "Intent to address unmet need:",
            "Available therapy landscape:",
            "Prior FDA interactions:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(product_description=oversized).to_prompt_text()
        section = text.split("Product description:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = RMATDesignationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True

    async def test_does_not_converge_when_evidence_stretch_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: uncontrolled small study\n"
            "EVIDENCE-STRETCH FLAGS:\n"
            "- The 18-patient single-arm study uses a surrogate endpoint not validated for potential\n"
            "SERIOUS-CONDITION FLAGS: None detected\n"
            "UNMET-NEED FLAGS: None detected\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = RMATDesignationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["evidence_stretch_flags"] == [
            "The 18-patient single-arm study uses a surrogate endpoint not validated for potential"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: uncontrolled small study\n"
            "EVIDENCE-STRETCH FLAGS:\n"
            "- The 18-patient single-arm study uses a surrogate endpoint not validated for potential\n"
            "RECOMMENDATION: add a controlled cohort\n"
            "SERIOUS-CONDITION FLAGS: None detected\n"
            "UNMET-NEED FLAGS: None detected\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = RMATDesignationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["evidence_stretch_flags"] == [
            "The 18-patient single-arm study uses a surrogate endpoint not validated for potential"
        ]


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = RMATDesignationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "evidence_stretch_flags",
            "serious_condition_flags",
            "unmet_need_flags",
            "rmat_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["rmat_checklist"][0] == "[OWNER: Regulatory Strategy]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = RMATDesignationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        below_critique = (
            "EVIDENCE-STRETCH FLAGS: None detected\n"
            "SERIOUS-CONDITION FLAGS: None detected\n"
            "UNMET-NEED FLAGS: None detected\n"
        )
        wf = RMATDesignationWorkflow(
            executor=FakeExecutor(["d1", "d2", "d3"]),
            reviewer=FakeReviewer([
                make_review(7.9, approved=False, critique=below_critique),
                make_review(7.9, approved=False, critique=below_critique),
                make_review(7.9, approved=False, critique=below_critique),
            ]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
