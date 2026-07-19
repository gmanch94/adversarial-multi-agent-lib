"""Unit tests for SubstantialEquivalence510kWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-2). Mirrors test_assay_performance_claim.py shape:
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when predicate-mismatch flags present (exact == assertion)
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
from adv_multi_agent.lifesciences.workflows.substantial_equivalence_510k import (
    SubstantialEquivalence510kWorkflow,
    SERequest,
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


def make_request(**kwargs: Any) -> SERequest:
    defaults: dict[str, Any] = dict(
        subject_device_description=(
            "A blood-glucose meter — a portable single-analyte photometric device "
            "with disposable test strips, intended for self-monitoring."
        ),
        intended_use=(
            "Quantitative measurement of glucose in fresh capillary whole blood."
        ),
        indications_for_use=(
            "For self-testing by people with diabetes at home (OTC) and by "
            "healthcare professionals in clinical settings."
        ),
        technological_characteristics=(
            "Amperometric glucose-oxidase test strip, 0.5 uL sample, 5-second "
            "readout, Bluetooth data export."
        ),
        candidate_predicates=(
            "A cleared blood-glucose meter of the same amperometric strip type and "
            "the same self-monitoring intended use."
        ),
        performance_data_summary=(
            "System accuracy per ISO 15197:2013; 99% of results within Zone A of "
            "the consensus error grid."
        ),
        differences_from_predicate=(
            "Subject adds a Bluetooth data-export module; predicate is display-only."
        ),
        prior_fda_interactions="No prior submissions for this device.",
    )
    defaults.update(kwargs)
    return SERequest(**defaults)


def clean_critique() -> str:
    return (
        "Predicate valid; indications within cleared scope; no new questions raised.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm Bluetooth module raises no new safety question\n"
        "PREDICATE-MISMATCH FLAGS: None detected\n"
        "INDICATION-CREEP FLAGS: None detected\n"
        "TECHNOLOGY-DELTA FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Predicate comparison
Candidate predicate shares the amperometric strip type and self-monitoring
intended use. Valid SE anchor.

## Intended use and indications
Subject indications match the predicate's cleared OTC + professional scope.

## Technological characteristics
Bluetooth data export is the only new characteristic; it does not alter the
measurement principle.

## Performance-data bridge
ISO 15197:2013 system accuracy supports the subject; data-export module has no
analytical impact.

## Substantial-equivalence conclusion
Subject device is substantially equivalent to the cited predicate.

## Claims
[Source: candidate_predicates] Predicate shares intended use and device type.
[Source: performance_data_summary] ISO 15197:2013 accuracy met.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Subject device description:",
            "Intended use:",
            "Indications for use:",
            "Technological characteristics:",
            "Candidate predicates:",
            "Performance-data summary:",
            "Differences from predicate:",
            "Prior FDA interactions:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(candidate_predicates=oversized).to_prompt_text()
        section = text.split("Candidate predicates:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = SubstantialEquivalence510kWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_predicate_mismatch_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: predicate intended use differs from subject\n"
            "PREDICATE-MISMATCH FLAGS:\n"
            "- Predicate has a different intended use (diagnostic vs monitoring)\n"
            "INDICATION-CREEP FLAGS: None detected\n"
            "TECHNOLOGY-DELTA FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = SubstantialEquivalence510kWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["predicate_mismatch_flags"] == [
            "Predicate has a different intended use (diagnostic vs monitoring)"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: predicate intended use differs from subject\n"
            "PREDICATE-MISMATCH FLAGS:\n"
            "- Predicate has a different intended use (diagnostic vs monitoring)\n"
            "RECOMMENDATION: select a predicate with matching intended use\n"
            "INDICATION-CREEP FLAGS: None detected\n"
            "TECHNOLOGY-DELTA FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = SubstantialEquivalence510kWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["predicate_mismatch_flags"] == [
            "Predicate has a different intended use (diagnostic vs monitoring)"
        ]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: no valid predicate for the broadened indication\n"
            "PREDICATE-MISMATCH FLAGS: None detected\n"
            "INDICATION-CREEP FLAGS: None detected\n"
            "TECHNOLOGY-DELTA FLAGS: None detected\n"
            "REVIEWER VETO: Predicate is cleared only for professional use; the "
            "subject broadens to OTC self-testing with no valid predicate for that "
            "indication. Asserting SE would misrepresent equivalence to FDA. "
            "Escalate to Regulatory Affairs; consider De Novo."
        )
        config = make_config(tmp_path)
        wf = SubstantialEquivalence510kWorkflow(
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
        assert "Predicate" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = SubstantialEquivalence510kWorkflow(
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
        wf = SubstantialEquivalence510kWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "subject_device_description",
            "predicate_mismatch_flags",
            "indication_creep_flags",
            "technology_delta_flags",
            "se_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["se_checklist"][0] == "[OWNER: Regulatory Affairs Lead]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = SubstantialEquivalence510kWorkflow(
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
            "PREDICATE-MISMATCH FLAGS: None detected\n"
            "INDICATION-CREEP FLAGS: None detected\n"
            "TECHNOLOGY-DELTA FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = SubstantialEquivalence510kWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
