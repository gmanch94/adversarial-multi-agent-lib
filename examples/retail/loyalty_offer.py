"""
Loyalty offer example — runs LoyaltyOfferWorkflow with synthetic Kroger
dairy-segment data and explicit allowed / disallowed attribute lists.

Demonstrates the fairness-gate pattern: reviewer challenges segment
criteria derived from disallowed proxies (ZIP, language, first-name,
inferred income, device model).

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.retail.loyalty_offer
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.retail.workflows.loyalty_offer import (
    LoyaltyOfferRequest,
    LoyaltyOfferWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = LoyaltyOfferRequest(
        customer_segment=(
            "High-engagement dairy buyers: loyalty members who purchased ≥4 distinct "
            "dairy SKUs in the last 60 days AND visited a store ≥3 times in the last "
            "90 days. Estimated segment size: 84,000 households across 220 stores."
        ),
        offer_proposal=(
            "-15% off Kroger private-label dairy SKUs, two-week redemption window, "
            "max 5 redemptions per household, valid both in-store and curbside pickup. "
            "Not stackable with category coupons."
        ),
        historical_response=(
            "2025 Q3 ran a similar -12% private-label dairy offer to a smaller segment "
            "(48K households). Results: 22% redemption rate within window, 3% measured "
            "free-rider rate vs holdout, $0.18/unit incremental contribution margin lift. "
            "Cannibalization on national-brand dairy was -7% of substituted units."
        ),
        margin_floor="$0.85 per unit (private-label dairy category floor for FY 2026)",
        allowed_attributes=[
            "purchase_history_60d",
            "loyalty_tier",
            "store_visits_90d",
            "category_basket_share",
            "lifetime_loyalty_value",
        ],
        disallowed_attributes=[
            "zip_code",
            "language_preference",
            "first_name",
            "household_income_inferred",
            "device_model",
            "payment_method_class",
            "name_n_grams",
        ],
        competing_offers=(
            "Regional competitor running -10% on national-brand dairy through Wk3. "
            "No concurrent internal dairy promo. Internal -5% bread-and-spread bundle "
            "active across all stores."
        ),
        gaming_risk=(
            "Basket-splitting across two transactions to maximise the 5-redemption cap. "
            "Spouse-account creation for a second household tranche. "
            "Coupon-stacking attempts with the bread-and-spread bundle (blocked at POS)."
        ),
    )

    workflow = LoyaltyOfferWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Segment: {result.metadata['segment_name']}")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for kind in ("fairness_flags", "margin_flags", "gaming_flags"):
        flags = result.metadata.get(kind) or []
        if flags:
            print(f"\n--- {kind.replace('_', ' ').title()} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
