"""
Private-label launch example — runs PrivateLabelWorkflow with a
synthetic better-tier coffee SKU.

Demonstrates the triple flag-gate pattern: reviewer challenges total-
category-margin math (incl. cannibalization), brand-fit, and supply
readiness (co-manufacturer audit + capacity).

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.retail.private_label
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.retail.workflows.private_label import (
    PrivateLabelRequest,
    PrivateLabelWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = PrivateLabelRequest(
        proposed_sku=(
            "SKU-PL-COFFEE-12oz — house-brand 'Hearth Reserve' single-origin "
            "Colombian medium-roast whole-bean coffee, 12oz bag. Better-tier "
            "of the house good-better-best ladder."
        ),
        target_price="$9.99 per 12oz bag",
        target_cost=(
            "$4.85 landed (green-bean $2.10, roasting + packaging $1.40, "
            "freight $0.35, co-manufacturer margin $1.00). Pricing locked Q1 "
            "with annual reopener."
        ),
        national_brand_baseline=(
            "Starbucks single-origin 12oz: $13.99 regular, ~22% category share. "
            "Peet's single-origin 12oz: $12.99, ~14% share. National-brand "
            "average margin to retailer: $4.20/bag."
        ),
        category_margin=(
            "Specialty whole-bean category: 32% gross margin to retailer "
            "blended; 38% for private-label tier, 28% for national-brand tier."
        ),
        cannibalization_estimate=(
            "From Starbucks single-origin: ~22% substitution. "
            "From Peet's single-origin: ~12% substitution. "
            "From existing private-label good-tier whole-bean: ~10% "
            "(intra-line trade-up). "
            "From competitor specialty cafés (away-from-home): negligible. "
            "Source: 2025 Q4 basket-share study, specialty-coffee subset."
        ),
        brand_positioning=(
            "'Hearth Reserve' is the better-tier sub-brand of the house brand. "
            "Better tier targets the consumer trading down from national-brand "
            "premium but unwilling to drop to value-tier. Sub-brand launched 18 "
            "months ago with 4 SKUs (tea, olive oil, balsamic, dark chocolate); "
            "this would be the first coffee SKU."
        ),
        quality_assurance=(
            "QA protocol: third-party cupping panel for every roast lot; "
            "moisture + density spec checks at roast; metal-detector + weight "
            "check at packaging. Recall readiness: lot traceability via roast-"
            "code + co-manufacturer batch ID; communication tree drafted for "
            "sub-brand 2024; retrieval-rate target 95% in 5 business days; "
            "regulatory notification per FDA 21 CFR Part 7."
        ),
        co_manufacturer=(
            "MountainPeak Roasters (anonymised). Last full GMP + HACCP audit: "
            "2024-11 (~6 months ago). Stated capacity: 180,000 lb/month "
            "single-origin. Demonstrated capacity at 95k/month on prior "
            "house-brand tea relationship (different SKU class)."
        ),
    )

    workflow = PrivateLabelWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Proposed SKU: {result.metadata['proposed_sku']}")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for kind in ("cannibalization_flags", "brand_flags", "supply_flags"):
        flags = result.metadata.get(kind) or []
        if flags:
            print(f"\n--- {kind.replace('_', ' ').title()} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
