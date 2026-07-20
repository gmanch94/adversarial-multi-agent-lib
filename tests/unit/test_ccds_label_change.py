"""Unit tests for CCDSLabelChangeWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-4) + D-LIFESCI-2 boundary vs the PV-signal
workflow: clean convergence, exact-flag non-convergence, sibling-header stop, veto
halt with first_draft, no-veto, metadata, disclaimer, threshold boundary,
module-docstring boundary statement.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.ccds_label_change import (
    CCDSLabelChangeRequest,
    CCDSLabelChangeWorkflow,
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


def make_request(**kwargs: Any) -> CCDSLabelChangeRequest:
    defaults: dict[str, Any] = dict(
        product_description="An established oral therapy marketed in multiple regions.",
        safety_signal_summary="A validated serious hepatic-injury signal has been "
                            "established and requires safety-labeling action.",
        proposed_ccds_change="Add a note about hepatic monitoring to the "
                          "Precautions section.",
        current_ccds_text="Current CCDS has no hepatic-injury language.",
        regional_label_status="Two of three markets plan the update; one market's "
                            "local label omits it.",
        regulatory_timelines="One region has an expedited safety-labeling "
                          "notification window.",
        implementation_plan="Roll out over the next two quarterly labeling cycles.",
        benefit_risk_context="Population-level benefit-risk remains positive with "
                          "monitoring.",
    )
    defaults.update(kwargs)
    return CCDSLabelChangeRequest(**defaults)


def clean_critique() -> str:
    return (
        "Wording faithful; regions consistent; clocks met.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm the local translation matches the CCDS\n"
        "SAFETY-SIGNAL FLAGS: None detected\n"
        "REGIONAL-DIVERGENCE FLAGS: None detected\n"
        "IMPLEMENTATION-CLOCK FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Signal-to-label fidelity
The proposed Warning wording conveys the established hepatic-injury signal.

## Regional consistency
All three markets reflect the change; no divergence.

## Timeline compliance
The plan meets the expedited notification window in the affected region.

## Benefit-risk and disposition
Wording is proportionate; the change may proceed.

## Claims
[Source: safety_signal_summary] A serious hepatic-injury signal is established.
[Source: regional_label_status] All markets reflect the change.
"""


def test_module_docstring_states_pv_signal_boundary() -> None:
    import adv_multi_agent.lifesciences.workflows.ccds_label_change as mod
    assert mod.__doc__ is not None
    doc = mod.__doc__.lower()
    assert "distinct from" in doc and "pharmacovigilancesignal" in doc.replace(" ", "")


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Safety signal summary:",
            "Proposed CCDS change:",
            "Current CCDS text:",
            "Regional label status:",
            "Regulatory timelines:",
            "Implementation plan:",
            "Benefit-risk context:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(safety_signal_summary=oversized).to_prompt_text()
        section = text.split("Safety signal summary:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CCDSLabelChangeWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_regional_divergence_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: one market missed\n"
            "SAFETY-SIGNAL FLAGS: None detected\n"
            "REGIONAL-DIVERGENCE FLAGS:\n"
            "- One market's local label omits the new hepatic warning without a documented rationale\n"
            "IMPLEMENTATION-CLOCK FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = CCDSLabelChangeWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["regional_divergence_flags"] == [
            "One market's local label omits the new hepatic warning without a documented rationale"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "SAFETY-SIGNAL FLAGS: None detected\n"
            "REGIONAL-DIVERGENCE FLAGS:\n"
            "- One market omits the warning\n"
            "RECOMMENDATION: align the local label\n"
            "IMPLEMENTATION-CLOCK FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = CCDSLabelChangeWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["regional_divergence_flags"] == ["One market omits the warning"]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: understated signal and a missed clock\n"
            "SAFETY-SIGNAL FLAGS: None detected\n"
            "REGIONAL-DIVERGENCE FLAGS: None detected\n"
            "IMPLEMENTATION-CLOCK FLAGS: None detected\n"
            "REVIEWER VETO: The proposed CCDS change downgrades an established "
            "serious hepatic risk to a precaution and misses a mandatory "
            "safety-labeling notification clock; it must not proceed as drafted. "
            "Escalate to Global Labeling."
        )
        config = make_config(tmp_path)
        wf = CCDSLabelChangeWorkflow(
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
        assert "proceed" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CCDSLabelChangeWorkflow(
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
        wf = CCDSLabelChangeWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "safety_signal_flags",
            "regional_divergence_flags",
            "implementation_clock_flags",
            "ccds_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["ccds_checklist"][0] == (
            "[OWNER: Global Labeling / Regulatory Affairs]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CCDSLabelChangeWorkflow(
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
        executor = FakeExecutor(["d1", "d2", "d3"])
        below_critique = (
            "SAFETY-SIGNAL FLAGS: None detected\n"
            "REGIONAL-DIVERGENCE FLAGS: None detected\n"
            "IMPLEMENTATION-CLOCK FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = CCDSLabelChangeWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
