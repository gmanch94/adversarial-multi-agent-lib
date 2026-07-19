"""Unit tests for CombinationProductPMOAWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.combination_product_pmoa import (
    CombinationProductPMOAWorkflow,
    PMOARequest,
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
        score_threshold=7.5,
    )
    defaults.update(kwargs)
    return Config(**defaults)


def make_review(
    score: float,
    *,
    approved: bool,
    critique: str = "",
    suggestions: list[str] | None = None,
) -> ReviewResult:
    return ReviewResult(
        score=score,
        critique=critique,
        suggestions=suggestions or [],
        approved=approved,
    )


def make_request(**kwargs: Any) -> PMOARequest:
    defaults: dict[str, Any] = dict(
        product_description="Prefilled single-dose autoinjector delivering a "
                            "biologic (drug/biologic + device constituents)",
        constituent_parts="Constituent A: a therapeutic biologic. "
                          "Constituent B: a single-use autoinjector device.",
        therapeutic_effect_mechanism="The biologic provides the therapeutic "
                                     "effect; the device delivers a fixed dose.",
        each_constituent_contribution="Biologic: primary therapeutic action. "
                                      "Device: delivery only, no therapeutic effect.",
        proposed_pmoa="Biologic mode of action (the biologic provides the "
                      "primary therapeutic effect)",
        proposed_lead_center="CBER",
        precedent_products="Prior prefilled biologic-delivery combination "
                          "products routed to CBER",
    )
    defaults.update(kwargs)
    return PMOARequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        request = make_request()
        text = request.to_prompt_text()
        assert "Product description:" in text
        assert "Constituent parts:" in text
        assert "Therapeutic effect mechanism:" in text
        assert "Each constituent contribution:" in text
        assert "Proposed PMOA:" in text
        assert "Proposed lead center:" in text
        assert "Precedent products:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        request = make_request(constituent_parts=oversized)
        text = request.to_prompt_text()
        section = text.split("Constituent parts:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Primary mode of action\nBiologic PMOA"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="PMOA FLAGS: None detected\n"
                         "LEAD-CENTER FLAGS: None detected\n"
                         "PATHWAY FLAGS: None detected",
            )
        ])
        wf = CombinationProductPMOAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_pmoa_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: PMOA does not follow from mechanism\n"
            "PMOA FLAGS:\n"
            "- Device PMOA asserted where the biologic provides the primary effect\n"
            "LEAD-CENTER FLAGS: None detected\n"
            "PATHWAY FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = CombinationProductPMOAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["pmoa_flags"] == [
            "Device PMOA asserted where the biologic provides the primary effect"
        ]

    async def test_does_not_converge_when_lead_center_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: center inconsistent with PMOA\n"
            "PMOA FLAGS: None detected\n"
            "LEAD-CENTER FLAGS:\n"
            "- Proposed CDRH lead center inconsistent with drug PMOA\n"
            "PATHWAY FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = CombinationProductPMOAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["lead_center_flags"] == [
            "Proposed CDRH lead center inconsistent with drug PMOA"
        ]

    async def test_does_not_converge_when_pathway_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "PMOA FLAGS: None detected\n"
            "LEAD-CENTER FLAGS: None detected\n"
            "PATHWAY FLAGS:\n"
            "- 510(k) pathway inconsistent with a CDER lead center\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = CombinationProductPMOAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["pathway_flags"] == [
            "510(k) pathway inconsistent with a CDER lead center"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "PMOA FLAGS: None detected\n"
            "LEAD-CENTER FLAGS:\n"
            "- Proposed CDRH lead center inconsistent with drug PMOA\n"
            "PATHWAY FLAGS:\n"
            "- 510(k) pathway inconsistent with a CDER lead center\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = CombinationProductPMOAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.metadata["lead_center_flags"] == [
            "Proposed CDRH lead center inconsistent with drug PMOA"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="PMOA FLAGS: None detected\n"
                         "LEAD-CENTER FLAGS:\n"
                         "- Proposed CDRH lead center inconsistent with drug PMOA\n"
                         "PATHWAY FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="PMOA FLAGS: None detected\n"
                         "LEAD-CENTER FLAGS: None detected\n"
                         "PATHWAY FLAGS: None detected",
            ),
        ])
        wf = CombinationProductPMOAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_keys_and_checklist_owner(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="PMOA FLAGS: None detected\n"
                         "LEAD-CENTER FLAGS: None detected\n"
                         "PATHWAY FLAGS: None detected",
            )
        ])
        wf = CombinationProductPMOAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert "pmoa_flags" in result.metadata
        assert "lead_center_flags" in result.metadata
        assert "pathway_flags" in result.metadata
        assert "pmoa_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata
        assert "product_description" in result.metadata
        checklist = result.metadata["pmoa_checklist"]
        assert checklist[0] == "[OWNER: Regulatory Strategy Lead]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="PMOA FLAGS: None detected\n"
                         "LEAD-CENTER FLAGS: None detected\n"
                         "PATHWAY FLAGS: None detected",
            )
        ])
        wf = CombinationProductPMOAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
        assert "ADVISORY" in _DISCLAIMER.upper()


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    """Zero flags but approved=False (score below threshold) must not converge."""

    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        clean_critique = (
            "PMOA FLAGS: None detected\n"
            "LEAD-CENTER FLAGS: None detected\n"
            "PATHWAY FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = CombinationProductPMOAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
