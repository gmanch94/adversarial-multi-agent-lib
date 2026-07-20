"""Unit tests for BioequivalenceWorkflow — no live API calls.

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
from adv_multi_agent.lifesciences.workflows.bioequivalence import (
    BioequivalenceRequest,
    BioequivalenceWorkflow,
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


def make_request(**kwargs: Any) -> BioequivalenceRequest:
    defaults: dict[str, Any] = dict(
        product_description="A generic modified-release oral tablet vs the "
                           "reference listed drug.",
        study_design="Two-way crossover, single dose, fed and fasting.",
        pk_parameters="AUC 90% CI within 80.00-125.00%; Cmax 90% CI reaches "
                     "128% under fed conditions.",
        study_population="36 healthy adult volunteers.",
        statistical_analysis="ANOVA on log-transformed parameters; intra-subject "
                           "CV moderate; no replicate design.",
        boundary_results="Cmax 90% CI upper bound crosses the 125% limit in the "
                        "fed study.",
        biowaiver_basis="No biowaiver claimed.",
        special_considerations="Not a narrow-therapeutic-index drug.",
    )
    defaults.update(kwargs)
    return BioequivalenceRequest(**defaults)


def clean_critique() -> str:
    return (
        "PK boundaries met; design appropriate; no waiver issues.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Report the intra-subject CV in the summary\n"
        "PK-BOUNDARY FLAGS: None detected\n"
        "STUDY-DESIGN FLAGS: None detected\n"
        "WAIVER-JUSTIFICATION FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## PK-boundary conformance
Both AUC and Cmax 90% confidence intervals fall within 80.00-125.00%.

## Study-design validity
The crossover design under fed and fasting conditions is appropriate.

## Waiver and limit justification
No biowaiver is claimed; standard limits apply.

## Bioequivalence conclusion
The test product is bioequivalent to the reference.

## Claims
[Source: study_design] A two-way crossover design was used.
[Source: pk_parameters] The AUC 90% CI is within limits.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Study design:",
            "PK parameters:",
            "Study population:",
            "Statistical analysis:",
            "Boundary results:",
            "Biowaiver basis:",
            "Special considerations:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(pk_parameters=oversized).to_prompt_text()
        section = text.split("PK parameters:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = BioequivalenceWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_pk_boundary_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: Cmax CI out of range\n"
            "PK-BOUNDARY FLAGS:\n"
            "- Cmax 90% CI upper bound at 128% is outside the bioequivalence limits\n"
            "STUDY-DESIGN FLAGS: None detected\n"
            "WAIVER-JUSTIFICATION FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = BioequivalenceWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["pk_boundary_flags"] == [
            "Cmax 90% CI upper bound at 128% is outside the bioequivalence limits"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.0/10\n"
            "PK-BOUNDARY FLAGS:\n"
            "- Cmax CI exceeds 125%\n"
            "RECOMMENDATION: repeat the fed study\n"
            "STUDY-DESIGN FLAGS: None detected\n"
            "WAIVER-JUSTIFICATION FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = BioequivalenceWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.0, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.metadata["pk_boundary_flags"] == ["Cmax CI exceeds 125%"]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: bioequivalence concluded despite an out-of-range CI\n"
            "PK-BOUNDARY FLAGS: None detected\n"
            "STUDY-DESIGN FLAGS: None detected\n"
            "WAIVER-JUSTIFICATION FLAGS: None detected\n"
            "REVIEWER VETO: Bioequivalence is concluded while the Cmax 90% "
            "confidence interval falls outside the accepted limits; it must not be "
            "concluded. Escalate to Clinical Pharmacology."
        )
        config = make_config(tmp_path)
        wf = BioequivalenceWorkflow(
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
        assert "concluded" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = BioequivalenceWorkflow(
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
        wf = BioequivalenceWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "pk_boundary_flags",
            "study_design_flags",
            "waiver_justification_flags",
            "bioequivalence_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["bioequivalence_checklist"][0] == (
            "[OWNER: Clinical Pharmacology / Regulatory]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = BioequivalenceWorkflow(
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
            "PK-BOUNDARY FLAGS: None detected\n"
            "STUDY-DESIGN FLAGS: None detected\n"
            "WAIVER-JUSTIFICATION FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        reviewer = FakeReviewer([
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
            make_review(7.9, approved=False, critique=below_critique),
        ])
        wf = BioequivalenceWorkflow(
            executor=executor,
            reviewer=reviewer,
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
