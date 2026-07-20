"""Unit tests for ColdChainExcursionWorkflow — no live API calls.

Veto + triple-flag (D-LIFESCI-4): clean convergence, exact-flag non-convergence,
sibling-header stop, veto halt with first_draft, no-veto, metadata, disclaimer,
threshold boundary.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.cold_chain_excursion import (
    ColdChainExcursionRequest,
    ColdChainExcursionWorkflow,
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


def make_request(**kwargs: Any) -> ColdChainExcursionRequest:
    defaults: dict[str, Any] = dict(
        product_description="A refrigerated biologic labeled for storage at "
                           "2-8 degrees Celsius.",
        excursion_description="Held on a loading dock and again at a distribution "
                             "hub above 8 degrees Celsius on two legs of transit.",
        label_storage_condition="Store at 2-8 degrees Celsius; do not freeze.",
        stability_budget_summary="Supporting stability shows a total allowable "
                                "excursion budget of 24 hours above 8 degrees.",
        excursion_extent="Leg one: 14 hours; leg two: 16 hours; cumulative "
                        "30 hours (not summed by the caller).",
        affected_units="Two shipper pallets from a single lot.",
        impact_on_quality="Caller states the product is unaffected because each "
                        "leg was brief.",
        proposed_disposition="Release.",
    )
    defaults.update(kwargs)
    return ColdChainExcursionRequest(**defaults)


def clean_critique() -> str:
    return (
        "Stability impact grounded; disposition consistent; scope summed.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Attach the MKT calculation to the file\n"
        "STABILITY-IMPACT FLAGS: None detected\n"
        "DISPOSITION FLAGS: None detected\n"
        "EXCURSION-SCOPE FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Excursion summary
The lot experienced two above-range legs; cumulative 30 hours over the label.

## Stability impact
Cumulative 30 hours exceeds the 24-hour stability budget; potency may be affected.

## Excursion scope
Two shipper pallets from one lot; cumulative excursion summed across both legs.

## Disposition
Quarantine pending confirmatory potency testing; do not release.

## Claims
[Source: stability_budget_summary] The allowable excursion budget is 24 hours.
[Source: excursion_extent] The cumulative excursion is 30 hours.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Excursion description:",
            "Label storage condition:",
            "Stability budget summary:",
            "Excursion extent:",
            "Affected units:",
            "Impact on quality:",
            "Proposed disposition:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(excursion_description=oversized).to_prompt_text()
        section = text.split("Excursion description:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ColdChainExcursionWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_excursion_scope_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: scope not summed\n"
            "STABILITY-IMPACT FLAGS: None detected\n"
            "DISPOSITION FLAGS: None detected\n"
            "EXCURSION-SCOPE FLAGS:\n"
            "- Cumulative time-out-of-range across two legs not summed for the affected lots\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = ColdChainExcursionWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["excursion_scope_flags"] == [
            "Cumulative time-out-of-range across two legs not summed for the affected lots"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "STABILITY-IMPACT FLAGS: None detected\n"
            "DISPOSITION FLAGS: None detected\n"
            "EXCURSION-SCOPE FLAGS:\n"
            "- Second leg excluded from the total\n"
            "RECOMMENDATION: recompute the MKT\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = ColdChainExcursionWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["excursion_scope_flags"] == ["Second leg excluded from the total"]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: release beyond the stability budget\n"
            "STABILITY-IMPACT FLAGS: None detected\n"
            "DISPOSITION FLAGS: None detected\n"
            "EXCURSION-SCOPE FLAGS: None detected\n"
            "REVIEWER VETO: A release is proposed for product whose cumulative "
            "excursion exceeds its stability budget with no supporting data; it "
            "must not be released. Escalate to Quality."
        )
        config = make_config(tmp_path)
        wf = ColdChainExcursionWorkflow(
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
        wf = ColdChainExcursionWorkflow(
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
        wf = ColdChainExcursionWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "stability_impact_flags",
            "disposition_flags",
            "excursion_scope_flags",
            "coldchain_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["coldchain_checklist"][0] == (
            "[OWNER: Quality / Cold-Chain Disposition]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = ColdChainExcursionWorkflow(
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
            "STABILITY-IMPACT FLAGS: None detected\n"
            "DISPOSITION FLAGS: None detected\n"
            "EXCURSION-SCOPE FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = ColdChainExcursionWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
