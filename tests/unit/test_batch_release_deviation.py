"""Unit tests for BatchReleaseDeviationWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-4):
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when criticality flags present (exact == assertion)
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
from adv_multi_agent.lifesciences.workflows.batch_release_deviation import (
    BatchReleaseDeviationWorkflow,
    BatchReleaseRequest,
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


def make_request(**kwargs: Any) -> BatchReleaseRequest:
    defaults: dict[str, Any] = dict(
        batch_identifier="Oral solid-dose immediate-release tablet, lot ABI-2026-114.",
        deviation_description=(
            "A mid-run tablet-weight excursion above the in-process action limit "
            "for approximately six minutes during compression."
        ),
        deviation_classification="Caller proposes minor.",
        affected_cqas="Tablet weight; potentially content uniformity.",
        impact_assessment_summary=(
            "Caller states weight returned to target; content uniformity not "
            "re-tested on the affected interval."
        ),
        root_cause_summary="Feed-frame speed drift; corrected mid-run.",
        capa_status="CAPA drafted to add a feed-frame interlock; not yet effective.",
        proposed_disposition="Release.",
    )
    defaults.update(kwargs)
    return BatchReleaseRequest(**defaults)


def clean_critique() -> str:
    return (
        "Disposition sound; criticality correct; CQA impact complete.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm the CAPA effectiveness date\n"
        "CRITICALITY FLAGS: None detected\n"
        "IMPACT-ASSESSMENT FLAGS: None detected\n"
        "RELEASE-RISK FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Deviation summary
A brief tablet-weight excursion occurred during compression and was corrected.

## Criticality classification
Classified major given the potential content-uniformity impact on the interval.

## Impact assessment
Content uniformity on the affected interval was re-tested and conforms.

## Release-risk judgment
No unresolved risk to the patient or the CQA after re-test.

## Root cause, CAPA, and disposition
Feed-frame speed drift; CAPA linked; disposition release after re-test.

## Claims
[Source: deviation_description] A weight excursion occurred during compression.
[Source: affected_cqas] Content uniformity was the CQA at risk.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Batch identifier:",
            "Deviation description:",
            "Deviation classification:",
            "Affected CQAs:",
            "Impact assessment summary:",
            "Root cause summary:",
            "CAPA status:",
            "Proposed disposition:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(deviation_description=oversized).to_prompt_text()
        section = text.split("Deviation description:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = BatchReleaseDeviationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_criticality_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: under-classified deviation\n"
            "CRITICALITY FLAGS:\n"
            "- Weight excursion touching content-uniformity CQA under-classified as minor\n"
            "IMPACT-ASSESSMENT FLAGS: None detected\n"
            "RELEASE-RISK FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = BatchReleaseDeviationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["criticality_flags"] == [
            "Weight excursion touching content-uniformity CQA under-classified as minor"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: under-classified deviation\n"
            "CRITICALITY FLAGS:\n"
            "- Excursion under-classified as minor\n"
            "RECOMMENDATION: re-classify and re-test content uniformity\n"
            "IMPACT-ASSESSMENT FLAGS: None detected\n"
            "RELEASE-RISK FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = BatchReleaseDeviationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["criticality_flags"] == ["Excursion under-classified as minor"]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: release of a non-conforming batch\n"
            "CRITICALITY FLAGS: None detected\n"
            "IMPACT-ASSESSMENT FLAGS: None detected\n"
            "RELEASE-RISK FLAGS: None detected\n"
            "REVIEWER VETO: The proposed release dispositions a batch with an "
            "unresolved critical deviation affecting a content-uniformity CQA; the "
            "batch must not be released. Escalate to the Qualified Person."
        )
        config = make_config(tmp_path)
        wf = BatchReleaseDeviationWorkflow(
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
        assert "released" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = BatchReleaseDeviationWorkflow(
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
        wf = BatchReleaseDeviationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "batch_identifier",
            "criticality_flags",
            "impact_assessment_flags",
            "release_risk_flags",
            "batch_release_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["batch_release_checklist"][0] == (
            "[OWNER: Qualified Person / Quality Release]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = BatchReleaseDeviationWorkflow(
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
            "CRITICALITY FLAGS: None detected\n"
            "IMPACT-ASSESSMENT FLAGS: None detected\n"
            "RELEASE-RISK FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = BatchReleaseDeviationWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
