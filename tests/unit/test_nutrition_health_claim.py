"""Unit tests for NutritionHealthClaimWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.nutrition_health_claim import (
    NutritionClaimRequest,
    NutritionHealthClaimWorkflow,
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


def make_request(**kwargs: Any) -> NutritionClaimRequest:
    defaults: dict[str, Any] = dict(
        product_category="Adult nutritional shake (ready-to-drink, oral)",
        claim_set="C-01 'supports muscle health' (structure-function); "
                  "C-02 'excellent source of protein' (nutrient-content); "
                  "C-03 '25 essential vitamins and minerals'",
        substantiation_dossier_summary="D-01 RCT on protein + muscle mass; "
                                       "D-02 nutrient composition analysis report",
        target_population="Adults 19+; not marketed to infants",
        nutrient_profile="Per serving: 30 g protein, 350 kcal, 25 vitamins/minerals "
                         "at 20-50% DV",
        allergen_declaration="Contains: soy. Manufactured on shared lines.",
        infant_formula_flag="No — general adult population",
    )
    defaults.update(kwargs)
    return NutritionClaimRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        request = make_request()
        text = request.to_prompt_text()
        assert "Product category:" in text
        assert "Claim set:" in text
        assert "Substantiation dossier summary:" in text
        assert "Target population:" in text
        assert "Nutrient profile:" in text
        assert "Allergen declaration:" in text
        assert "Infant formula flag:" in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        request = make_request(claim_set=oversized)
        text = request.to_prompt_text()
        section = text.split("Claim set:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Claim inventory\nAll claims substantiated"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="CLAIM-SUBSTANTIATION FLAGS: None detected\n"
                         "NUTRIENT-ADEQUACY FLAGS: None detected\n"
                         "ALLERGEN FLAGS: None detected",
            )
        ])
        wf = NutritionHealthClaimWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_claim_substantiation_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: unsubstantiated claim\n"
            "CLAIM-SUBSTANTIATION FLAGS:\n"
            "- C-01 lacks competent-reliable evidence in the dossier\n"
            "NUTRIENT-ADEQUACY FLAGS: None detected\n"
            "ALLERGEN FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = NutritionHealthClaimWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["claim_substantiation_flags"] == [
            "C-01 lacks competent-reliable evidence in the dossier"
        ]

    async def test_does_not_converge_when_nutrient_adequacy_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "CLAIM-SUBSTANTIATION FLAGS: None detected\n"
            "NUTRIENT-ADEQUACY FLAGS:\n"
            "- Iron below the 21 CFR 107 infant-formula minimum\n"
            "ALLERGEN FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = NutritionHealthClaimWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["nutrient_adequacy_flags"] == [
            "Iron below the 21 CFR 107 infant-formula minimum"
        ]

    async def test_does_not_converge_when_allergen_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: undeclared allergen\n"
            "CLAIM-SUBSTANTIATION FLAGS: None detected\n"
            "NUTRIENT-ADEQUACY FLAGS: None detected\n"
            "ALLERGEN FLAGS:\n- Undeclared major allergen: milk\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = NutritionHealthClaimWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["allergen_flags"] == ["Undeclared major allergen: milk"]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "CLAIM-SUBSTANTIATION FLAGS: None detected\n"
            "NUTRIENT-ADEQUACY FLAGS: None detected\n"
            "ALLERGEN FLAGS:\n- Undeclared major allergen: milk\n"
            "RECOMMENDATION: hold the label release\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = NutritionHealthClaimWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.metadata["allergen_flags"] == ["Undeclared major allergen: milk"]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="CLAIM-SUBSTANTIATION FLAGS: None detected\n"
                         "NUTRIENT-ADEQUACY FLAGS: None detected\n"
                         "ALLERGEN FLAGS:\n- Undeclared major allergen: milk",
            ),
            make_review(
                9.0, approved=True,
                critique="CLAIM-SUBSTANTIATION FLAGS: None detected\n"
                         "NUTRIENT-ADEQUACY FLAGS: None detected\n"
                         "ALLERGEN FLAGS: None detected",
            ),
        ])
        wf = NutritionHealthClaimWorkflow(
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
                critique="CLAIM-SUBSTANTIATION FLAGS: None detected\n"
                         "NUTRIENT-ADEQUACY FLAGS: None detected\n"
                         "ALLERGEN FLAGS: None detected",
            )
        ])
        wf = NutritionHealthClaimWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert "claim_substantiation_flags" in result.metadata
        assert "nutrient_adequacy_flags" in result.metadata
        assert "allergen_flags" in result.metadata
        assert "nutrition_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata
        assert "product_category" in result.metadata
        checklist = result.metadata["nutrition_checklist"]
        assert checklist[0] == "[OWNER: Nutrition Regulatory + Scientific Affairs]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="CLAIM-SUBSTANTIATION FLAGS: None detected\n"
                         "NUTRIENT-ADEQUACY FLAGS: None detected\n"
                         "ALLERGEN FLAGS: None detected",
            )
        ])
        wf = NutritionHealthClaimWorkflow(
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
            "CLAIM-SUBSTANTIATION FLAGS: None detected\n"
            "NUTRIENT-ADEQUACY FLAGS: None detected\n"
            "ALLERGEN FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = NutritionHealthClaimWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
