"""Unit tests for PharmacovigilanceSignalWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-4) + D-LIFESCI-2 healthcare boundary:
- module docstring states the healthcare boundary (D-LIFESCI-2)
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when signal-strength flags present (exact == assertion)
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
from adv_multi_agent.lifesciences.workflows.pharmacovigilance_signal import (
    PharmacovigilanceSignalWorkflow,
    PVSignalRequest,
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


def make_request(**kwargs: Any) -> PVSignalRequest:
    defaults: dict[str, Any] = dict(
        product_description="An established oral small-molecule product, marketed "
                        "for over a decade.",
        signal_description="A rising number of serious hepatic injury reports.",
        data_source="Spontaneous safety database plus a quarterly "
                 "disproportionality run.",
        case_series_summary="Forty serious hepatic cases over the trailing year, "
                        "several with positive dechallenge.",
        disproportionality_metrics="EBGM elevated above the review threshold; ROR "
                              "lower bound above 1.",
        causality_assessment="Caller assesses causality as unlikely, citing "
                        "confounding by comorbidity.",
        current_labeling="Hepatic injury is NOT currently in the product labeling.",
        proposed_action="Continue routine monitoring; no label change.",
    )
    defaults.update(kwargs)
    return PVSignalRequest(**defaults)


def clean_critique() -> str:
    return (
        "Signal well characterized; causality sound; action reflects impact.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm the next PSUR cycle\n"
        "SIGNAL-STRENGTH FLAGS: None detected\n"
        "CAUSALITY FLAGS: None detected\n"
        "LABELING-IMPACT FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Signal summary
A hepatic-injury signal for an established oral product from spontaneous reports.

## Signal strength
The disproportionality is characterized as strong and consistent with the cases.

## Causality assessment
Population-level causality is assessed as at least possible with an explicit basis.

## Labeling / regulatory impact
The signal implies a labeling evaluation; the action reflects that.

## Recommended action
Formal signal evaluation with a labeling assessment.

## Claims
[Source: disproportionality_metrics] The EBGM is above the review threshold.
[Source: current_labeling] Hepatic injury is not currently labeled.
"""


def test_module_docstring_states_healthcare_boundary() -> None:
    import adv_multi_agent.lifesciences.workflows.pharmacovigilance_signal as mod
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "distinct from" in doc and "adverseeventtriage" in doc.replace(" ", "")


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Signal description:",
            "Data source:",
            "Case series summary:",
            "Disproportionality metrics:",
            "Causality assessment:",
            "Current labeling:",
            "Proposed action:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(signal_description=oversized).to_prompt_text()
        section = text.split("Signal description:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = PharmacovigilanceSignalWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_signal_strength_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: understated signal\n"
            "SIGNAL-STRENGTH FLAGS:\n"
            "- Disproportionality for the hepatic event understated relative to EBGM\n"
            "CAUSALITY FLAGS: None detected\n"
            "LABELING-IMPACT FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = PharmacovigilanceSignalWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["signal_strength_flags"] == [
            "Disproportionality for the hepatic event understated relative to EBGM"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "SIGNAL-STRENGTH FLAGS:\n"
            "- Signal understated relative to the metrics\n"
            "RECOMMENDATION: open a formal signal evaluation\n"
            "CAUSALITY FLAGS: None detected\n"
            "LABELING-IMPACT FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = PharmacovigilanceSignalWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["signal_strength_flags"] == [
            "Signal understated relative to the metrics"
        ]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: under-escalated signal\n"
            "SIGNAL-STRENGTH FLAGS: None detected\n"
            "CAUSALITY FLAGS: None detected\n"
            "LABELING-IMPACT FLAGS: None detected\n"
            "REVIEWER VETO: A serious unlabeled hepatic signal meeting the "
            "threshold for labeling action is characterized as no-action; it "
            "requires formal evaluation and likely a labeling change. Escalate to "
            "the Safety Physician."
        )
        config = make_config(tmp_path)
        wf = PharmacovigilanceSignalWorkflow(
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
        assert "labeling" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = PharmacovigilanceSignalWorkflow(
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
        wf = PharmacovigilanceSignalWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "signal_strength_flags",
            "causality_flags",
            "labeling_impact_flags",
            "pv_signal_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["pv_signal_checklist"][0] == (
            "[OWNER: Pharmacovigilance / Safety Physician]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = PharmacovigilanceSignalWorkflow(
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
            "SIGNAL-STRENGTH FLAGS: None detected\n"
            "CAUSALITY FLAGS: None detected\n"
            "LABELING-IMPACT FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = PharmacovigilanceSignalWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
