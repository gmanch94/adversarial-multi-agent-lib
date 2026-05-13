"""Unit tests for PrivateLabelWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.retail.workflows.private_label import (
    PrivateLabelRequest,
    PrivateLabelWorkflow,
    _DISCLAIMER,
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


def make_result(
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


def make_request(**kwargs: Any) -> PrivateLabelRequest:
    defaults: dict[str, Any] = dict(
        proposed_sku="SKU-PL-COFFEE-12oz Hearth Reserve single-origin Colombian medium",
        target_price="$9.99/12oz",
        target_cost="$4.85 landed (green $2.10 + roast/pack $1.40 + freight $0.35 + comfg $1.00)",
        national_brand_baseline=(
            "Starbucks 12oz $13.99 / 22% share. Peet's 12oz $12.99 / 14% share. "
            "NB avg margin to retailer $4.20/bag."
        ),
        category_margin="Specialty whole-bean 32% blended; PL tier 38%; NB tier 28%",
        cannibalization_estimate=(
            "Starbucks 22%; Peet's 12%; intra-line trade-up 10%; away-from-home cafés negligible. "
            "Source: 2025 Q4 basket study."
        ),
        brand_positioning=(
            "Hearth Reserve = better-tier sub-brand; first coffee SKU (4 prior SKUs: tea, "
            "olive oil, balsamic, dark chocolate); 18mo since sub-brand launch."
        ),
        quality_assurance=(
            "3rd-party cupping per lot; moisture + density at roast; metal + weight at pack. "
            "Recall: roast-code traceability; 95% retrieval in 5 BDs; FDA 21 CFR Part 7."
        ),
        co_manufacturer=(
            "MountainPeak Roasters. Last GMP+HACCP 2024-11 (~6mo ago). Stated capacity "
            "180k lb/mo single-origin. Demonstrated 95k/mo on prior tea SKU."
        ),
    )
    defaults.update(kwargs)
    return PrivateLabelRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> PrivateLabelWorkflow:
    return PrivateLabelWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Cannibalization Math
Substitution decomposed: Starbucks 22% (lost NB margin $4.20 × units), Peet's
12% ($4.10 × units), intra-line 10% ($3.80 × units), away-from-home negligible.
Per private-label unit margin $9.99 − $4.85 = $5.14. Central-case total-
category-margin delta positive by ~$0.42/unit on weighted basis. Adverse case
(rates at upper plausible band): $0.18/unit positive.

## Brand Fit
Hearth Reserve is the better-tier sub-brand; price $9.99 sits below NB ($12.99–
$13.99) by ~25%, inside the 15–30% private-label band. Sub-brand identity
established 18 months; coffee fits the specialty-pantry adjacency.

## Supply Readiness
MountainPeak Roasters audit 2024-11 (~6mo), full GMP + HACCP. Stated capacity
180k/mo; demonstrated 95k/mo. Pilot run required to validate capacity at
single-origin SKU class.

## Pricing + Margin Stack
Retailer GM: $5.14 / 51.5% — above category 38% PL tier, consistent with
better-tier ladder. Cost stack decomposed: green $2.10 + roast/pack $1.40 +
freight $0.35 + comfg margin $1.00.

## Launch Plan
Pilot 200-store regional launch quarter 1; full rollout pending pilot read.
Shelf placement: adjacent to NB premium, not value-tier. Price-ladder
disclosure: shelf strip naming better-tier sub-brand.

## Success Metric + Kill Criteria
Metric: total-category-margin delta positive at p50 + 6 weeks. Kill: QA
finding, capacity miss, or adverse-case delta negative.

## Evidence Gaps
Single-origin capacity at MountainPeak is asserted, not demonstrated;
pilot-run validation required.

## Claims
[Source: cannibalization_estimate] Starbucks substitution rate stated at 22%.
[Source: co_manufacturer] MountainPeak last GMP+HACCP audit 2024-11.
[Source: brand_positioning] Hearth Reserve is the better-tier sub-brand with 4 prior SKUs.
[Source: category_margin] Specialty whole-bean private-label tier margin is 38%.
"""

_CLEAN_CRITIQUE = """\
Solid recommendation.

Overall score: 8.3/10
Key issues:
- Pilot-run validation of single-origin capacity is the correct gate before scale.

CANNIBALIZATION FLAGS: None detected
BRAND FLAGS: None detected
SUPPLY FLAGS: None detected
"""


class TestPrivateLabelConvergence:
    @pytest.mark.asyncio
    async def test_converges_when_no_flags(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1

    @pytest.mark.asyncio
    async def test_does_not_converge_when_cannibalization_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "Overall score: 7.8/10\nKey issues: adverse case negative\n"
            "CANNIBALIZATION FLAGS:\n- Adverse-case total-category margin delta is -$0.05/unit\n"
            "BRAND FLAGS: None detected\nSUPPLY FLAGS: None detected"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.8, approved=True, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Adverse-case" in f for f in result.metadata["cannibalization_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_brand_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "CANNIBALIZATION FLAGS: None detected\n"
            "BRAND FLAGS:\n- Better-tier positioning at value-tier price ladder\n"
            "SUPPLY FLAGS: None detected\nOverall score: 7.0/10"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.0, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("Better-tier" in f for f in result.metadata["brand_flags"])

    @pytest.mark.asyncio
    async def test_does_not_converge_when_supply_flag_present(
        self, tmp_path: Path
    ) -> None:
        critique = (
            "CANNIBALIZATION FLAGS: None detected\nBRAND FLAGS: None detected\n"
            "SUPPLY FLAGS:\n- Single-origin capacity asserted but never demonstrated at volume\n"
            "Overall score: 7.5/10"
        )
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=1)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(7.5, approved=False, critique=critique)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert any("asserted" in f for f in result.metadata["supply_flags"])


class TestPrivateLabelOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_metadata_keys_present(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        for key in (
            "proposed_sku",
            "cannibalization_flags",
            "brand_flags",
            "supply_flags",
            "approver_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata

    @pytest.mark.asyncio
    async def test_claims_registered(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer([make_result(8.3, approved=True, critique=_CLEAN_CRITIQUE)])
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["ledger_summary"]["total"] >= 4


class TestPrivateLabelRequestPromptText:
    def test_renders_all_labels(self) -> None:
        text = make_request().to_prompt_text()
        for label in [
            "Proposed SKU:",
            "Target price:",
            "Target cost:",
            "National-brand baseline:",
            "Category margin:",
            "Cannibalization estimate:",
            "Brand positioning:",
            "Quality assurance:",
            "Co-manufacturer:",
        ]:
            assert label in text


class TestBuildApproverChecklist:
    def test_checklist_includes_per_flag_callouts(self) -> None:
        accumulated = {
            "CANNIBALIZATION FLAGS:": ["adverse negative"],
            "BRAND FLAGS:": ["tier mismatch"],
            "SUPPLY FLAGS:": ["audit stale"],
        }
        items = PrivateLabelWorkflow._build_approver_checklist(
            make_request(), accumulated
        )
        flag_items = "\n".join(items)
        assert "CANNIBALIZATION FLAGS DETECTED" in flag_items
        assert "BRAND FLAGS DETECTED" in flag_items
        assert "SUPPLY FLAGS DETECTED" in flag_items

    def test_checklist_baseline_items_always_present(self) -> None:
        empty = {
            h: [] for h in ("CANNIBALIZATION FLAGS:", "BRAND FLAGS:", "SUPPLY FLAGS:")
        }
        items = PrivateLabelWorkflow._build_approver_checklist(make_request(), empty)
        text = "\n".join(items)
        assert "Category-management review" in text
        assert "Brand leadership" in text
        assert "QA sign-off" in text
        assert "Sourcing sign-off" in text
