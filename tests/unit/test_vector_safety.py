"""Unit tests for VectorSafetyWorkflow (Lifesciences CGT · no-veto) — no live API.

Triple-flag no-veto (D-LIFESCI-6). Mirrors the design-control no-veto shape:
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when RCR-RCL-RISK flags present (exact == assertion)
- sibling-header stop (trailing RECOMMENDATION: not slurped)
- all metadata keys present + checklist owner
- disclaimer in output
- threshold boundary (approved=False must not converge)
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.vector_safety import (
    VectorSafetyWorkflow,
    VectorSafetyRequest,
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


def make_request(**kwargs: Any) -> VectorSafetyRequest:
    defaults: dict[str, Any] = dict(
        vector_description=(
            "A third-generation self-inactivating lentiviral vector encoding a "
            "chimeric antigen receptor for ex-vivo T-cell modification."
        ),
        rcr_rcl_testing_summary=(
            "RCL testing by co-culture amplification with an ELISA/PCR endpoint on "
            "end-of-production cells and the vector supernatant; 5% cell-equivalent "
            "sampling."
        ),
        integration_profile_data=(
            "Integration-site analysis by LAM-PCR on the drug product; polyclonal "
            "distribution, no dominant clone above threshold."
        ),
        insertional_mutagenesis_assessment=(
            "Risk assessed as low given SIN design and polyclonal integration; "
            "clonal-expansion monitoring planned in the LTFU."
        ),
        oncogenicity_or_tumorigenicity_data=(
            "No tumorigenicity signal in the nonclinical model; genotoxicity "
            "in-vitro assay negative."
        ),
        vector_copy_number=(
            "Mean vector copy number 2.1 per cell; acceptance criterion <= 5 per cell."
        ),
        nonclinical_biodistribution=(
            "Biodistribution in the animal model showed transient signal limited to "
            "lymphoid tissue, cleared by day 90."
        ),
        long_term_followup_plan=(
            "15-year LTFU per the applicable guidance, with periodic RCL and "
            "clonality monitoring."
        ),
    )
    defaults.update(kwargs)
    return VectorSafetyRequest(**defaults)


def clean_critique() -> str:
    return (
        "RCR/RCL adequate; integration polyclonal; oncogenicity case sufficient.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm LTFU enrolment commitment\n"
        "RCR-RCL-RISK FLAGS: None detected\n"
        "INSERTIONAL-MUTAGENESIS FLAGS: None detected\n"
        "ONCOGENICITY FLAGS: None detected\n"
    )


_GOOD_OUTPUT = """\
## RCR/RCL testing
Co-culture amplification with a PCR endpoint on end-of-production cells is
adequate for a SIN lentiviral vector.

## Integration and insertional-mutagenesis
Polyclonal integration; no dominant clone. Copy number within the acceptance
criterion.

## Oncogenicity and tumorigenicity
No tumorigenicity signal; genotoxicity negative.

## Biodistribution and long-term follow-up
Transient lymphoid signal cleared by day 90; 15-year LTFU planned.

## Gaps and recommendations
Confirm the LTFU enrolment commitment.

## Claims
[Source: rcr_rcl_testing_summary] RCL testing uses co-culture amplification.
[Source: vector_copy_number] Mean VCN 2.1, criterion <= 5.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Vector description:",
            "RCR/RCL testing summary:",
            "Integration profile data:",
            "Insertional-mutagenesis assessment:",
            "Oncogenicity / tumorigenicity data:",
            "Vector copy number:",
            "Nonclinical biodistribution:",
            "Long-term follow-up plan:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(vector_description=oversized).to_prompt_text()
        section = text.split("Vector description:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = VectorSafetyWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True

    async def test_does_not_converge_when_rcr_rcl_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: RCL sampling too small\n"
            "RCR-RCL-RISK FLAGS:\n"
            "- RCL co-culture sampling of 5% is below the vector-class expectation\n"
            "INSERTIONAL-MUTAGENESIS FLAGS: None detected\n"
            "ONCOGENICITY FLAGS: None detected\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = VectorSafetyWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["rcr_rcl_risk_flags"] == [
            "RCL co-culture sampling of 5% is below the vector-class expectation"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: RCL sampling too small\n"
            "RCR-RCL-RISK FLAGS:\n"
            "- RCL co-culture sampling of 5% is below the vector-class expectation\n"
            "RECOMMENDATION: increase the RCL sampling fraction\n"
            "INSERTIONAL-MUTAGENESIS FLAGS: None detected\n"
            "ONCOGENICITY FLAGS: None detected\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = VectorSafetyWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["rcr_rcl_risk_flags"] == [
            "RCL co-culture sampling of 5% is below the vector-class expectation"
        ]


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = VectorSafetyWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "vector_description",
            "rcr_rcl_risk_flags",
            "insertional_mutagenesis_flags",
            "oncogenicity_flags",
            "vector_safety_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["vector_safety_checklist"][0] == "[OWNER: Biosafety / Nonclinical Safety]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = VectorSafetyWorkflow(
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
    """L-HEALTH-3: zero flags but approved=False (below threshold) must not converge."""

    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        below_critique = (
            "RCR-RCL-RISK FLAGS: None detected\n"
            "INSERTIONAL-MUTAGENESIS FLAGS: None detected\n"
            "ONCOGENICITY FLAGS: None detected\n"
        )
        wf = VectorSafetyWorkflow(
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
