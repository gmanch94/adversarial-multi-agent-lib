"""
Promo / markdown example — runs PromoMarkdownWorkflow with a synthetic
Memorial Day cola-12-pack promo.

Demonstrates the triple flag-gate pattern: reviewer challenges
elasticity claim, margin math (with cannibalization), and timing
collisions.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.retail.promo_markdown
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.retail.workflows.promo_markdown import (
    PromoMarkdownWorkflow,
    PromoRequest,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = PromoRequest(
        sku="SKU-44210-COLA12",
        category="beverages (carbonated soft drinks)",
        current_price="$6.49 per 12-pack 12oz cans",
        inventory_on_hand=(
            "DC: 14,400 cases. Stores combined: 3,200 cases. Run rate ~4,160 "
            "cases/week so 4.2 weeks of supply at current pace."
        ),
        weeks_of_supply="4.2 weeks at run rate; supply not at clearance pressure",
        competitor_pricing=(
            "Competitor A regular price $5.99 12-pack. Competitor A Memorial Day "
            "promo: $4.99 12-pack, Wk2 of our window. Competitor B regular $6.29; "
            "no concurrent promo. Private-label 12-pack at $4.49 regular."
        ),
        elasticity_estimate=(
            "Category benchmark from 2025 Q4 region-level price-test: -1.4 ± 0.3 "
            "for 20–25% off depth on national-brand 12-pack carbonated soft drinks. "
            "Source: corporate pricing-science team report."
        ),
        margin_floor=(
            "$0.42 per 12-pack contribution margin floor for FY 2026. "
            "Adverse-case margin must hold this floor."
        ),
        promo_window="2026-05-25 through 2026-06-01 (Memorial Day week through Sunday)",
        cannibalization_risk=(
            "Private-label 12-pack cola: substitution rate ~25% historically. "
            "Same brand 8-pack 16oz bottles: rate ~12%. "
            "Sports drink 12-pack same brand: rate ~5% (cross-need substitution). "
            "Diet variant 12-pack: rate ~8% (intra-line trade)."
        ),
    )

    workflow = PromoMarkdownWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"SKU: {result.metadata['sku']} | Category: {result.metadata['category']}")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for kind in ("elasticity_flags", "margin_flags", "timing_flags"):
        flags = result.metadata.get(kind) or []
        if flags:
            print(f"\n--- {kind.replace('_', ' ').title()} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
