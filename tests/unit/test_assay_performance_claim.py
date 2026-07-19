"""Unit tests for AssayPerformanceClaimWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-2). Mirrors test_adverse_event_triage.py shape:
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when sensitivity flags present (exact == assertion)
- sibling-header stop (trailing RECOMMENDATION: not slurped)
- veto halts loop with first_draft preserved
- no veto when directive is None
- all metadata keys present on clean run
- disclaimer in output on clean run
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.assay_performance_claim import (
    AssayPerformanceClaimWorkflow,
    AssayClaimRequest,
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


def make_request(**kwargs: Any) -> AssayClaimRequest:
    defaults: dict[str, Any] = dict(
        assay_description="A rapid antigen test (lateral-flow immunoassay cassette).",
        intended_use=(
            "Qualitative detection of a viral antigen in nasal swab specimens from "
            "symptomatic individuals within the first 5 days of symptom onset."
        ),
        analyte_measurand="Viral nucleoprotein antigen; visual line intensity readout.",
        claim_set=(
            "Sensitivity 99% (nasal swab, symptomatic); Specificity 98.5%; "
            "shelf life 24 months at 2–30°C."
        ),
        study_design_summary=(
            "Prospective clinical study, n=180 PCR-positive, RT-PCR reference "
            "method, CLSI EP12 qualitative protocol."
        ),
        interference_panel_tested=(
            "Nasal-swab matrix: mucin, blood, common nasal sprays tested. "
            "Saliva matrix NOT tested."
        ),
        cross_reactivity_data="Tested against 12 respiratory pathogens; no cross-reactivity observed.",
        stability_claims="24-month shelf life supported by accelerated + 18-month real-time data.",
    )
    defaults.update(kwargs)
    return AssayClaimRequest(**defaults)


def clean_critique() -> str:
    return (
        "Claim mapping thorough; each performance claim stays within the study CI.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm CLSI EP12 population representativeness\n"
        "SENSITIVITY-CLAIM FLAGS: None detected\n"
        "SPECIFICITY-CLAIM FLAGS: None detected\n"
        "INTERFERENCE FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Claim-by-claim data mapping
Sensitivity 99% claim maps to clinical study n=180 (RT-PCR reference, CLSI EP12).
Specificity 98.5% maps to the same study's PCR-negative arm.

## Sensitivity assessment
Point estimate 99% with n=180; lower 95% CI bound 94%. Claim re-stated as
"sensitivity 96% (95% CI 94–99%)" to stay within the lower bound.

## Specificity assessment
Specificity 98.5% supported by the negative arm; CI within claim.

## Interference and cross-reactivity
Nasal-swab matrix interferents tested. Saliva matrix untested — not claimed.

## Recommended claim set
Sensitivity 96% (95% CI 94–99%), nasal swab, symptomatic; specificity 98.5%.

## Claims
[Source: claim_set] Sensitivity claim re-stated within the study lower CI bound.
[Source: study_design_summary] CLSI EP12 protocol, n=180, RT-PCR reference.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Assay description:",
            "Intended use:",
            "Analyte / measurand:",
            "Claim set:",
            "Study design summary:",
            "Interference panel tested:",
            "Cross-reactivity data:",
            "Stability claims:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(claim_set=oversized).to_prompt_text()
        claim_section = text.split("Claim set:")[1].split("\n")[0]
        assert len(claim_section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = AssayPerformanceClaimWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_sensitivity_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: sensitivity claim exceeds study lower CI bound\n"
            "SENSITIVITY-CLAIM FLAGS:\n- Sensitivity claim 99% exceeds lower CI bound 94%\n"
            "SPECIFICITY-CLAIM FLAGS: None detected\n"
            "INTERFERENCE FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = AssayPerformanceClaimWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["sensitivity_claim_flags"] == [
            "Sensitivity claim 99% exceeds lower CI bound 94%"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: sensitivity claim exceeds study lower CI bound\n"
            "SENSITIVITY-CLAIM FLAGS:\n"
            "- Sensitivity claim 99% exceeds lower CI bound 94%\n"
            "RECOMMENDATION: re-state the claim as 96% (95% CI 94-99%)\n"
            "SPECIFICITY-CLAIM FLAGS: None detected\n"
            "INTERFERENCE FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = AssayPerformanceClaimWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["sensitivity_claim_flags"] == [
            "Sensitivity claim 99% exceeds lower CI bound 94%"
        ]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: sensitivity claim overstated relative to study CI\n"
            "SENSITIVITY-CLAIM FLAGS: None detected\n"
            "SPECIFICITY-CLAIM FLAGS: None detected\n"
            "INTERFERENCE FLAGS: None detected\n"
            "REVIEWER VETO: Sensitivity claim 99% is not supported by the study "
            "(n=180, lower 95% CI bound 94%); releasing it risks false-negative "
            "misdiagnosis and an adulteration/misbranding exposure. Do not release "
            "the claim; escalate to Diagnostics Regulatory."
        )
        config = make_config(tmp_path)
        wf = AssayPerformanceClaimWorkflow(
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
        assert "Sensitivity" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = AssayPerformanceClaimWorkflow(
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
        wf = AssayPerformanceClaimWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "assay_description",
            "sensitivity_claim_flags",
            "specificity_claim_flags",
            "interference_flags",
            "assay_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["assay_checklist"][0] == "[OWNER: Diagnostics Regulatory + R&D]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = AssayPerformanceClaimWorkflow(
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
    """L-HEALTH-3: zero flags + no veto but approved=False (score below threshold) must not converge."""

    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        below_critique = (
            "SENSITIVITY-CLAIM FLAGS: None detected\n"
            "SPECIFICITY-CLAIM FLAGS: None detected\n"
            "INTERFERENCE FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = AssayPerformanceClaimWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
