"""Unit tests for FieldActionClassificationWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-3) + D-LIFESCI-2 industrial boundary. Mirrors
test_device_reportability.py:
- to_prompt_text renders all fields + per-field cap
- module docstring states the industrial boundary (D-LIFESCI-2)
- convergence on clean input
- non-convergence when recall-class flags present (exact == assertion)
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
from adv_multi_agent.lifesciences.workflows.field_action_classification import (
    FieldActionClassificationWorkflow,
    FieldActionRequest,
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


def make_request(**kwargs: Any) -> FieldActionRequest:
    defaults: dict[str, Any] = dict(
        problem_description=(
            "A calibration-drift defect in a lot of a point-of-care analyzer can "
            "return low results; the defect is confined to a single production lot."
        ),
        health_hazard_evaluation=(
            "Low probability of temporary harm; no reasonable probability of "
            "serious adverse health consequences for the affected lot."
        ),
        affected_lots_serials="A single production lot of the analyzer.",
        distribution_scope="Distributed to clinics in two regions.",
        action_type="A field correction (software recalibration in the field).",
        root_cause_summary="A calibration-table error introduced at manufacture.",
        patient_exposure_estimate="An estimated few hundred devices in the field.",
        prior_related_actions="No prior related field actions on this product line.",
    )
    defaults.update(kwargs)
    return FieldActionRequest(**defaults)


def clean_critique() -> str:
    return (
        "Classification sound; class consistent with the hazard; reportability "
        "correctly characterised.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm the lot list is complete for the root cause\n"
        "RECALL-CLASS FLAGS: None detected\n"
        "CORRECTION-REMOVAL FLAGS: None detected\n"
        "HEALTH-HAZARD FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Problem and root cause
A calibration-drift defect confined to a single production lot of the analyzer.

## Health-hazard evaluation
Low probability of temporary harm; no serious adverse health consequences.

## Recall classification
The proposed class is consistent with the stated health hazard.

## Correction vs removal reportability
The action is a reportable correction and is characterised as such.

## Scope (lots / distribution)
The affected lot and its distribution are complete for the root cause.

## Claims
[Source: health_hazard_evaluation] No serious adverse health consequences.
[Source: affected_lots_serials] A single production lot is affected.
"""


def test_module_docstring_states_industrial_boundary() -> None:
    import adv_multi_agent.lifesciences.workflows.field_action_classification as mod
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "distinct from" in doc and "recallscopemanufacturing" in doc.replace(" ", "")


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Problem description:",
            "Health-hazard evaluation:",
            "Affected lots/serials:",
            "Distribution scope:",
            "Action type:",
            "Root cause summary:",
            "Patient exposure estimate:",
            "Prior related actions:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(problem_description=oversized).to_prompt_text()
        section = text.split("Problem description:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = FieldActionClassificationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_recall_class_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: a Class I hazard proposed as Class II\n"
            "RECALL-CLASS FLAGS:\n"
            "- Class II proposed where serious-harm probability indicates Class I\n"
            "CORRECTION-REMOVAL FLAGS: None detected\n"
            "HEALTH-HAZARD FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = FieldActionClassificationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["recall_class_flags"] == [
            "Class II proposed where serious-harm probability indicates Class I"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: a Class I hazard proposed as Class II\n"
            "RECALL-CLASS FLAGS:\n"
            "- Class II proposed where serious-harm probability indicates Class I\n"
            "RECOMMENDATION: re-derive the class from the health hazard\n"
            "CORRECTION-REMOVAL FLAGS: None detected\n"
            "HEALTH-HAZARD FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = FieldActionClassificationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["recall_class_flags"] == [
            "Class II proposed where serious-harm probability indicates Class I"
        ]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: a Class I hazard proposed as Class II\n"
            "RECALL-CLASS FLAGS: None detected\n"
            "CORRECTION-REMOVAL FLAGS: None detected\n"
            "HEALTH-HAZARD FLAGS: None detected\n"
            "REVIEWER VETO: The classification proposes Class II for a defect with "
            "a reasonable probability of serious adverse health consequences, which "
            "is a Class I recall, and calls a reportable removal a stock recovery. "
            "Escalate to the Recall committee; do not under-scope the action."
        )
        config = make_config(tmp_path)
        wf = FieldActionClassificationWorkflow(
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
        assert "Class I" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = FieldActionClassificationWorkflow(
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
        wf = FieldActionClassificationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "action_type",
            "recall_class_flags",
            "correction_removal_flags",
            "health_hazard_flags",
            "field_action_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["field_action_checklist"][0] == (
            "[OWNER: Recall Committee / Chief Quality Officer]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = FieldActionClassificationWorkflow(
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
            "RECALL-CLASS FLAGS: None detected\n"
            "CORRECTION-REMOVAL FLAGS: None detected\n"
            "HEALTH-HAZARD FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = FieldActionClassificationWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
