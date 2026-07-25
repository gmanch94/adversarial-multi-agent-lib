"""Unit tests for CGTLotReleaseSpecWorkflow (Lifesciences CGT · no-veto) — no live API.

Triple-flag no-veto (D-LIFESCI-8). Mirrors the no-veto shape.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.cgt_lot_release_spec import (
    CGTLotReleaseSpecWorkflow,
    LotReleaseSpecRequest,
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


def make_request(**kwargs: Any) -> LotReleaseSpecRequest:
    defaults: dict[str, Any] = dict(
        product_description=(
            "An autologous gene-modified cell therapy, cryopreserved single patient "
            "dose."
        ),
        proposed_release_specifications=(
            "Identity by flow phenotype; purity by residual-bead count; potency by a "
            "cytotoxicity assay; sterility by compendial method; endotoxin by LAL; "
            "viability by 7-AAD >= 70%."
        ),
        lot_size_and_format="Single autologous dose, ~50 mL cryobag.",
        shelf_life_and_storage="18 months at <= -150 C vapour-phase liquid nitrogen.",
        rapid_or_real_time_methods=(
            "Rapid sterility by an automated growth-based system; mycoplasma by qPCR "
            "released before the 28-day compendial confirmatory result."
        ),
        sterility_and_mycoplasma_strategy=(
            "Rapid method with conditional release; compendial sterility runs in "
            "parallel."
        ),
        out_of_specification_handling=(
            "OOS triggers quarantine and an investigation; no auto-release."
        ),
        stability_program_summary=(
            "Stability at the storage condition supports the 18-month shelf life with "
            "potency and viability trending."
        ),
    )
    defaults.update(kwargs)
    return LotReleaseSpecRequest(**defaults)


def clean_critique() -> str:
    return (
        "All release attributes covered; sampling practical; release strategy justified.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm potency assay linkage separately\n"
        "SPEC-COVERAGE FLAGS: None detected\n"
        "SMALL-LOT FLAGS: None detected\n"
        "SHELF-LIFE FLAGS: None detected\n"
    )


_GOOD_OUTPUT = """\
## Release-attribute coverage
Identity, purity, potency, sterility, safety, and viability each have a
specification with an acceptance criterion.

## Small-lot sampling
Sampling consumes a defined fraction compatible with the single-dose format.

## Short-shelf-life release
Rapid sterility with conditional release, compendial in parallel; justified.

## Stability and out-of-specification handling
Stability supports 18 months; OOS quarantines.

## Gaps and recommendations
Confirm the potency assay MoA-linkage in the dedicated potency review.

## Claims
[Source: proposed_release_specifications] Viability criterion is 7-AAD >= 70%.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Proposed release specifications:",
            "Lot size and format:",
            "Shelf life and storage:",
            "Rapid / real-time methods:",
            "Sterility and mycoplasma strategy:",
            "Out-of-specification handling:",
            "Stability program summary:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(product_description=oversized).to_prompt_text()
        section = text.split("Product description:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTLotReleaseSpecWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True

    async def test_does_not_converge_when_spec_coverage_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: no safety spec\n"
            "SPEC-COVERAGE FLAGS:\n"
            "- No residual-vector safety specification for an integrating construct\n"
            "SMALL-LOT FLAGS: None detected\n"
            "SHELF-LIFE FLAGS: None detected\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = CGTLotReleaseSpecWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["spec_coverage_flags"] == [
            "No residual-vector safety specification for an integrating construct"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: no safety spec\n"
            "SPEC-COVERAGE FLAGS:\n"
            "- No residual-vector safety specification for an integrating construct\n"
            "RECOMMENDATION: add a residual-vector safety criterion\n"
            "SMALL-LOT FLAGS: None detected\n"
            "SHELF-LIFE FLAGS: None detected\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = CGTLotReleaseSpecWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["spec_coverage_flags"] == [
            "No residual-vector safety specification for an integrating construct"
        ]


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTLotReleaseSpecWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "spec_coverage_flags",
            "small_lot_flags",
            "shelf_life_flags",
            "lot_release_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["lot_release_checklist"][0] == "[OWNER: Quality Control / Quality Engineering]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = CGTLotReleaseSpecWorkflow(
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
        below_critique = (
            "SPEC-COVERAGE FLAGS: None detected\n"
            "SMALL-LOT FLAGS: None detected\n"
            "SHELF-LIFE FLAGS: None detected\n"
        )
        wf = CGTLotReleaseSpecWorkflow(
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
