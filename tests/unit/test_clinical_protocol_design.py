"""Unit tests for ClinicalProtocolDesignWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-4):
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when power flags present (exact == assertion)
- sibling-header stop (trailing RECOMMENDATION: not slurped)
- veto halts loop with first_draft preserved
- no veto when directive is None
- all metadata keys present on clean run
- disclaimer in output on clean run
- threshold boundary
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.clinical_protocol_design import (
    ClinicalProtocolDesignWorkflow,
    ClinicalProtocolRequest,
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


def make_request(**kwargs: Any) -> ClinicalProtocolRequest:
    defaults: dict[str, Any] = dict(
        protocol_synopsis="Phase 2 randomized trial of an investigational "
                       "drug-eluting device for a peripheral vascular indication.",
        primary_endpoint="Change in a non-validated imaging surrogate at 6 months.",
        secondary_endpoints="Target-lesion revascularization; quality-of-life score.",
        statistical_plan_summary="n=60 per arm; power assumes a large effect size; "
                            "single interim analysis.",
        population_eligibility="Adults with the indication; excludes severe "
                          "comorbidity.",
        safety_monitoring_plan="Investigator review at each visit; no pre-specified "
                          "stopping rule for bleeding.",
        known_risks="Known procedural bleeding risk with the device class.",
        comparator_control="Active comparator device.",
    )
    defaults.update(kwargs)
    return ClinicalProtocolRequest(**defaults)


def clean_critique() -> str:
    return (
        "Endpoint valid; power adequate; safety monitoring sufficient.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm the DSMB charter\n"
        "ENDPOINT FLAGS: None detected\n"
        "POWER FLAGS: None detected\n"
        "SAFETY-MONITORING FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Protocol summary
Phase 2 randomized trial of a drug-eluting device for a vascular indication.

## Endpoint validity
The primary endpoint is a validated clinical measure supporting the objective.

## Statistical power
Sample size and power are justified by a conservative effect-size assumption.

## Safety monitoring
A DSMB and a pre-specified bleeding stopping rule are in place.

## Ethics and population
Eligibility is proportionate to the risk with vulnerable-population safeguards.

## Claims
[Source: primary_endpoint] The primary endpoint measures the objective.
[Source: known_risks] Procedural bleeding is a known risk for the device class.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Protocol synopsis:",
            "Primary endpoint:",
            "Secondary endpoints:",
            "Statistical plan summary:",
            "Population eligibility:",
            "Safety monitoring plan:",
            "Known risks:",
            "Comparator control:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(protocol_synopsis=oversized).to_prompt_text()
        section = text.split("Protocol synopsis:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalProtocolDesignWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_power_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: underpowered study\n"
            "ENDPOINT FLAGS: None detected\n"
            "POWER FLAGS:\n"
            "- Sample size assumes an unjustified effect size; study is underpowered\n"
            "SAFETY-MONITORING FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = ClinicalProtocolDesignWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["power_flags"] == [
            "Sample size assumes an unjustified effect size; study is underpowered"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "ENDPOINT FLAGS: None detected\n"
            "POWER FLAGS:\n"
            "- Study is underpowered for the effect\n"
            "RECOMMENDATION: recompute the sample size\n"
            "SAFETY-MONITORING FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = ClinicalProtocolDesignWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["power_flags"] == ["Study is underpowered for the effect"]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: subjects exposed to undue risk\n"
            "ENDPOINT FLAGS: None detected\n"
            "POWER FLAGS: None detected\n"
            "SAFETY-MONITORING FLAGS: None detected\n"
            "REVIEWER VETO: The protocol lacks a pre-specified stopping rule for a "
            "known serious bleeding risk, exposing subjects to undue risk; it must "
            "not proceed as designed. Escalate to the Medical Monitor."
        )
        config = make_config(tmp_path)
        wf = ClinicalProtocolDesignWorkflow(
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
        assert "risk" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalProtocolDesignWorkflow(
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
        wf = ClinicalProtocolDesignWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "protocol_synopsis",
            "endpoint_flags",
            "power_flags",
            "safety_monitoring_flags",
            "clinical_protocol_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["clinical_protocol_checklist"][0] == (
            "[OWNER: Clinical Development / Medical Monitor]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ClinicalProtocolDesignWorkflow(
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
    """Zero flags + no veto but approved=False (score below threshold) must not converge."""

    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        below_critique = (
            "ENDPOINT FLAGS: None detected\n"
            "POWER FLAGS: None detected\n"
            "SAFETY-MONITORING FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = ClinicalProtocolDesignWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
