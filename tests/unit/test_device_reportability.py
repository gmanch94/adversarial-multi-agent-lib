"""Unit tests for DeviceReportabilityWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-3) + D-LIFESCI-2 healthcare boundary. Mirrors
test_promotional_off_label_review.py:
- to_prompt_text renders all fields + per-field cap
- module docstring states the healthcare boundary (D-LIFESCI-2)
- convergence on clean input
- non-convergence when reportability flags present (exact == assertion)
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
from adv_multi_agent.lifesciences.workflows.device_reportability import (
    DeviceReportabilityWorkflow,
    ReportabilityRequest,
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


def make_request(**kwargs: Any) -> ReportabilityRequest:
    defaults: dict[str, Any] = dict(
        complaint_narrative=(
            "A user reported that an infusion pump under-delivered a scheduled "
            "dose; the patient recovered without lasting harm."
        ),
        device_identifier="An infusion pump (large-volume, general-ward class).",
        event_outcome="Transient under-infusion; patient recovered fully.",
        patient_impact="No lasting harm; graded as a minor, non-serious event.",
        malfunction_recurrence_potential=(
            "The occlusion-sensor fault is unlikely to recur after the firmware fix."
        ),
        prior_similar_events_count="Two prior similar events over the trailing year.",
        market_regions="United States and European Union.",
        date_became_aware="The manufacturer became aware on the reporting date.",
    )
    defaults.update(kwargs)
    return ReportabilityRequest(**defaults)


def clean_critique() -> str:
    return (
        "Determination sound; outcome graded correctly; no masked trend.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm the statutory clock for the EU market\n"
        "REPORTABILITY FLAGS: None detected\n"
        "SERIOUS-INJURY FLAGS: None detected\n"
        "MALFUNCTION-TREND FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Event summary
An infusion pump under-delivered a scheduled dose; the patient recovered fully.

## Reportability determination
The event does not meet a reporting definition; non-reportable, with the trend
basis checked below.

## Outcome grading
The outcome is a transient, non-serious event; no under-grading.

## Malfunction-trend assessment
Prior similar events do not cross the trend trigger after the firmware fix.

## Statutory clock and report path
No report required; the clock is documented for completeness per region.

## Claims
[Source: event_outcome] The patient recovered without lasting harm.
[Source: prior_similar_events_count] Prior events do not cross the trend trigger.
"""


def test_module_docstring_states_healthcare_boundary() -> None:
    import adv_multi_agent.lifesciences.workflows.device_reportability as mod
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "distinct from" in doc and "adverseeventtriage" in doc.replace(" ", "")


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Complaint narrative:",
            "Device identifier:",
            "Event outcome:",
            "Patient impact:",
            "Malfunction recurrence potential:",
            "Prior similar events count:",
            "Market regions:",
            "Date became aware:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(complaint_narrative=oversized).to_prompt_text()
        section = text.split("Complaint narrative:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = DeviceReportabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_reportability_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: a reportable serious injury coded non-reportable\n"
            "REPORTABILITY FLAGS:\n"
            "- Serious injury coded non-reportable\n"
            "SERIOUS-INJURY FLAGS: None detected\n"
            "MALFUNCTION-TREND FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = DeviceReportabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["reportability_flags"] == ["Serious injury coded non-reportable"]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: a reportable serious injury coded non-reportable\n"
            "REPORTABILITY FLAGS:\n"
            "- Serious injury coded non-reportable\n"
            "RECOMMENDATION: re-apply the reporting definition and file the report\n"
            "SERIOUS-INJURY FLAGS: None detected\n"
            "MALFUNCTION-TREND FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = DeviceReportabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["reportability_flags"] == ["Serious injury coded non-reportable"]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: a reportable serious injury coded non-reportable\n"
            "REPORTABILITY FLAGS: None detected\n"
            "SERIOUS-INJURY FLAGS: None detected\n"
            "MALFUNCTION-TREND FLAGS: None detected\n"
            "REVIEWER VETO: The determination codes a serious injury requiring "
            "intervention as non-reportable, but it meets the 21 CFR 803 serious "
            "injury definition and is reportable. Escalate to the Vigilance "
            "officer; initiate the report within the statutory clock."
        )
        config = make_config(tmp_path)
        wf = DeviceReportabilityWorkflow(
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
        assert "reportable" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = DeviceReportabilityWorkflow(
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
        wf = DeviceReportabilityWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "device_identifier",
            "reportability_flags",
            "serious_injury_flags",
            "malfunction_trend_flags",
            "reportability_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["reportability_checklist"][0] == (
            "[OWNER: Post-market Surveillance / Vigilance Officer]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = DeviceReportabilityWorkflow(
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
            "REPORTABILITY FLAGS: None detected\n"
            "SERIOUS-INJURY FLAGS: None detected\n"
            "MALFUNCTION-TREND FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = DeviceReportabilityWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
