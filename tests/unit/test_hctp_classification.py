"""Unit tests for HCTPClassificationWorkflow (Lifesciences CGT · veto) — no live API.

Veto + triple-flag (D-LIFESCI-8). Mirrors the se510k veto shape.
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.hctp_classification import (
    HCTPClassificationWorkflow,
    HCTPClassificationRequest,
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


def make_request(**kwargs: Any) -> HCTPClassificationRequest:
    defaults: dict[str, Any] = dict(
        product_description=(
            "A minimally-processed structural-tissue allograft (decellularised "
            "dermal matrix) intended for soft-tissue repair."
        ),
        cellular_tissue_source="Allogeneic cadaveric dermis.",
        manufacturing_steps=(
            "Cleaning, decellularisation, and terminal packaging; no cell expansion "
            "and no chemical modification of the collagen scaffold."
        ),
        minimal_manipulation_rationale=(
            "Processing removes cells but preserves the original structural collagen "
            "matrix, keeping the relevant structural characteristics unaltered."
        ),
        intended_use_homology=(
            "Used for soft-tissue repair / covering — the original structural "
            "function of dermis (homologous)."
        ),
        combination_with_another_article="Not combined with any drug or device.",
        systemic_effect_or_metabolic_dependence=(
            "No systemic effect; acts as a structural scaffold, not dependent on "
            "living-cell metabolism."
        ),
        proposed_regulatory_tier="361 HCT/P.",
        precedent_determinations=(
            "Comparable decellularised dermal matrices have been regulated as 361 "
            "HCT/Ps for homologous structural use."
        ),
    )
    defaults.update(kwargs)
    return HCTPClassificationRequest(**defaults)


def clean_critique() -> str:
    return (
        "Minimal manipulation preserved; homologous structural use; no combination or systemic effect.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm terminal sterilisation does not alter the matrix\n"
        "MINIMAL-MANIPULATION FLAGS: None detected\n"
        "HOMOLOGOUS-USE FLAGS: None detected\n"
        "TIER-CLASSIFICATION FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Minimal manipulation (prong 1)
Decellularisation preserves the structural collagen matrix; minimally manipulated.

## Homologous use (prong 2)
Soft-tissue repair is the original structural function of dermis; homologous.

## Combination and systemic effect (prongs 3 and 4)
Not combined; no systemic effect; not dependent on living-cell metabolism.

## Tier conclusion
The product is a 361 HCT/P.

## Precedent
Consistent with precedent for decellularised dermal matrices.

## Claims
[Source: manufacturing_steps] No cell expansion or chemical modification.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Cellular / tissue source:",
            "Manufacturing steps:",
            "Minimal-manipulation rationale:",
            "Intended use / homology:",
            "Combination with another article:",
            "Systemic effect / metabolic dependence:",
            "Proposed regulatory tier:",
            "Precedent determinations:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(manufacturing_steps=oversized).to_prompt_text()
        section = text.split("Manufacturing steps:")[1].split("\n")[0]
        assert len(section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestH1FullRequestReachesExecutor:
    """H-1 / D-A11-6: the whole request must reach the round-1 executor prompt.

    9 fields x ~1.4k = ~12.6k, far above the retired 6000-char post-concat cap.
    Under that guillotine the trailing fields (here the 9th, carrying the
    1271.10(a) prongs / precedent) were cut off the executor prompt entirely,
    and since the reviewer only sees the executor draft, that evidence left the
    whole adversarial loop. This drives a real `run()` — G7 catches a call site
    that keeps the old cap statically; this catches it behaviourally.
    """

    async def test_trailing_field_survives_to_executor_prompt(self, tmp_path: Path) -> None:
        filler = "x" * 1400
        tail = "PRECEDENT_SENTINEL_H1"
        big = dict(
            product_description="PD " + filler,
            cellular_tissue_source="CT " + filler,
            manufacturing_steps="MS " + filler,
            minimal_manipulation_rationale="MM " + filler,
            intended_use_homology="IU " + filler,
            combination_with_another_article="CB " + filler,
            systemic_effect_or_metabolic_dependence="SE " + filler,
            proposed_regulatory_tier="PT " + filler,
            precedent_determinations=tail + " " + filler,
        )
        executor = FakeExecutor(responses=[_GOOD_OUTPUT])
        wf = HCTPClassificationWorkflow(
            executor=executor,
            reviewer=FakeReviewer(
                results=[make_review(8.5, approved=True, critique=clean_critique())]
            ),
            config=make_config(tmp_path),
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        await wf.run(request=make_request(**big))
        assert executor.prompts, "executor was never called"
        assert tail in executor.prompts[0], (
            "the last request field was cut off the round-1 executor prompt — the "
            "H-1 6000-char post-concat guillotine has returned (D-A11-6)."
        )


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = HCTPClassificationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_minimal_manipulation_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: processing alters characteristics\n"
            "MINIMAL-MANIPULATION FLAGS:\n"
            "- Enzymatic cross-linking alters the relevant structural characteristics\n"
            "HOMOLOGOUS-USE FLAGS: None detected\n"
            "TIER-CLASSIFICATION FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = HCTPClassificationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["minimal_manipulation_flags"] == [
            "Enzymatic cross-linking alters the relevant structural characteristics"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: processing alters characteristics\n"
            "MINIMAL-MANIPULATION FLAGS:\n"
            "- Enzymatic cross-linking alters the relevant structural characteristics\n"
            "RECOMMENDATION: pursue the 351 pathway\n"
            "HOMOLOGOUS-USE FLAGS: None detected\n"
            "TIER-CLASSIFICATION FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = HCTPClassificationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["minimal_manipulation_flags"] == [
            "Enzymatic cross-linking alters the relevant structural characteristics"
        ]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: non-homologous systemic use\n"
            "MINIMAL-MANIPULATION FLAGS: None detected\n"
            "HOMOLOGOUS-USE FLAGS: None detected\n"
            "TIER-CLASSIFICATION FLAGS: None detected\n"
            "REVIEWER VETO: The product is expanded and formulated for a metabolic "
            "systemic effect, not a homologous structural use; it is a 351 biologic. "
            "Asserting the 361 tier would bypass the BLA and misrepresent regulatory "
            "status. Pursue the BLA pathway."
        )
        config = make_config(tmp_path)
        wf = HCTPClassificationWorkflow(
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
        assert "351 biologic" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_trailing_clean_echo_does_not_suppress_the_halt(self, tmp_path: Path) -> None:
        """D-A11-5 at the workflow level — the test that would have caught the defect.

        G1–G6 compare code to code and code to prompt; this defect lived in
        runtime critique text, so only driving a real critique through `run()`
        recomputes the safety property. Pre-fix (last-wins) this converged
        clean with no banner while the reviewer had flagged and halted.
        """
        echoed_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: non-homologous systemic use\n"
            "MINIMAL-MANIPULATION FLAGS:\n"
            "- Cells are expanded ex vivo, altering the relevant characteristics\n"
            "HOMOLOGOUS-USE FLAGS: None detected\n"
            "TIER-CLASSIFICATION FLAGS: None detected\n"
            "REVIEWER VETO: The product is a 351 biologic; do not assert the 361 tier.\n"
            "\n"
            "For reference, the draft under review contained the following text:\n"
            "MINIMAL-MANIPULATION FLAGS: None detected\n"
            "HOMOLOGOUS-USE FLAGS: None detected\n"
            "TIER-CLASSIFICATION FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path)
        wf = HCTPClassificationWorkflow(
            executor=FakeExecutor(responses=["initial draft", "draft2", "draft3"]),
            reviewer=FakeReviewer(results=[make_review(9.0, approved=True, critique=echoed_critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["vetoed"] is True
        assert "351 biologic" in result.metadata["veto_reason"]
        assert _VETO_BANNER in result.output
        assert "VETO DIRECTIVE: The product is a 351 biologic" in result.output
        assert result.metadata["minimal_manipulation_flags"] == [
            "Cells are expanded ex vivo, altering the relevant characteristics"
        ]

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = HCTPClassificationWorkflow(
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
        wf = HCTPClassificationWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "minimal_manipulation_flags",
            "homologous_use_flags",
            "tier_classification_flags",
            "hctp_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["hctp_checklist"][0] == "[OWNER: Regulatory Affairs Lead (CBER pathway)]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = HCTPClassificationWorkflow(
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
            "MINIMAL-MANIPULATION FLAGS: None detected\n"
            "HOMOLOGOUS-USE FLAGS: None detected\n"
            "TIER-CLASSIFICATION FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        wf = HCTPClassificationWorkflow(
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
