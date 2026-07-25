"""Unit tests for CGTDurabilityClaimWorkflow (Lifesciences CGT · veto) — no live API.

Veto + triple-flag (D-LIFESCI-6). Mirrors the se510k veto shape.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.cgt_durability_claim import (
    CGTDurabilityClaimWorkflow,
    DurabilityClaimRequest,
    _DISCLAIMER,
    _MAX_FIELD_CHARS,
    _VETO_BANNER,
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


def make_request(**kwargs: Any) -> DurabilityClaimRequest:
    defaults: dict[str, Any] = dict(
        product_description="A one-time AAV gene therapy for a monogenic disorder.",
        proposed_claim=(
            "Provides durable disease control through 2 years of follow-up."
        ),
        pivotal_efficacy_summary=(
            "The pivotal study met its primary endpoint with a significant reduction "
            "in the disease biomarker."
        ),
        followup_duration_and_n=(
            "36 patients dosed; median follow-up 26 months; low censoring through 24 "
            "months."
        ),
        durability_evidence=(
            "No loss of response observed through 24 months; expression maintained."
        ),
        population_and_endpoint=(
            "Adults with the disorder; endpoint is a validated disease biomarker."
        ),
        comparator_or_natural_history=(
            "Natural history shows progressive decline absent treatment."
        ),
        label_context="Claim proposed for the clinical-efficacy section of the label.",
    )
    defaults.update(kwargs)
    return DurabilityClaimRequest(**defaults)


def clean_critique() -> str:
    return (
        "Claim within follow-up; evidence sufficient; no curative overreach.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm censoring beyond 24 months\n"
        "DURABILITY-CLAIM FLAGS: None detected\n"
        "FOLLOWUP-EVIDENCE FLAGS: None detected\n"
        "CURATIVE-LANGUAGE FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Durability vs follow-up
The 2-year claim stays within the 24-month observed follow-up.

## Follow-up evidence
36 patients, median 26 months, low censoring; supports persistence through 24 months.

## Curative language
No curative language used; claim is durability-limited.

## Comparator / natural-history context
Natural history shows decline absent treatment.

## Claim conclusion
The durability claim is supported through the observed follow-up.

## Claims
[Source: followup_duration_and_n] Median follow-up 26 months, 36 patients.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Proposed claim:",
            "Pivotal efficacy summary:",
            "Follow-up duration and n:",
            "Durability evidence:",
            "Population and endpoint:",
            "Comparator / natural history:",
            "Label context:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(proposed_claim=oversized).to_prompt_text()
        section = text.split("Proposed claim:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTDurabilityClaimWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_durability_claim_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: claim beyond follow-up\n"
            "DURABILITY-CLAIM FLAGS:\n"
            "- The 2-year claim exceeds the 14-month median follow-up\n"
            "FOLLOWUP-EVIDENCE FLAGS: None detected\n"
            "CURATIVE-LANGUAGE FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = CGTDurabilityClaimWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["durability_claim_flags"] == [
            "The 2-year claim exceeds the 14-month median follow-up"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: claim beyond follow-up\n"
            "DURABILITY-CLAIM FLAGS:\n"
            "- The 2-year claim exceeds the 14-month median follow-up\n"
            "RECOMMENDATION: narrow to 12 months\n"
            "FOLLOWUP-EVIDENCE FLAGS: None detected\n"
            "CURATIVE-LANGUAGE FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = CGTDurabilityClaimWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["durability_claim_flags"] == [
            "The 2-year claim exceeds the 14-month median follow-up"
        ]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: curative overreach\n"
            "DURABILITY-CLAIM FLAGS: None detected\n"
            "FOLLOWUP-EVIDENCE FLAGS: None detected\n"
            "CURATIVE-LANGUAGE FLAGS: None detected\n"
            "REVIEWER VETO: The claim states the therapy is curative on a 6-month "
            "biomarker with no durability data; this overstates benefit and creates "
            "misbranding and patient-harm exposure. Remove the curative claim and "
            "limit to the observed window."
        )
        config = make_config(tmp_path)
        wf = CGTDurabilityClaimWorkflow(
            executor=FakeExecutor(responses=["initial draft", "draft2", "draft3"]),
            reviewer=FakeReviewer(results=[make_review(9.0, approved=True, critique=veto_critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert "veto_reason" in result.metadata
        assert "misbranding" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTDurabilityClaimWorkflow(
            executor=FakeExecutor(responses=["draft"]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert "veto_reason" not in result.metadata
        assert "vetoed" not in result.metadata


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTDurabilityClaimWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "durability_claim_flags",
            "followup_evidence_flags",
            "curative_language_flags",
            "durability_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["durability_checklist"][0] == "[OWNER: Regulatory Affairs + Medical Affairs]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTDurabilityClaimWorkflow(
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
            "DURABILITY-CLAIM FLAGS: None detected\n"
            "FOLLOWUP-EVIDENCE FLAGS: None detected\n"
            "CURATIVE-LANGUAGE FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        wf = CGTDurabilityClaimWorkflow(
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
