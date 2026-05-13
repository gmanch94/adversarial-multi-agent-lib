"""
Demand Forecast example — runs DemandForecastWorkflow with synthetic Kroger data.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.retail.demand_forecasting
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.retail.workflows.demand_forecasting import (
    DemandForecastWorkflow,
    ForecastRequest,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = ForecastRequest(
        store_id="KRO-OH-0042",
        sku="SKU-88210-MILK2PCT",
        product_category="dairy",
        historical_sales=(
            "Wk1:320 Wk2:310 Wk3:335 Wk4:340 "
            "Wk5:315 Wk6:328 Wk7:342 Wk8:330"
        ),
        current_inventory="on-hand: 180 units; in-transit: 200 units (arrives Thu)",
        lead_time_days="3",
        upcoming_events=(
            "Memorial Day weekend in Wk3 (Mon holiday, high grilling traffic); "
            "store loyalty promo -10% on dairy Wk2 only"
        ),
        seasonality_notes=(
            "Dairy demand historically rises 6–10% May–Aug in this region "
            "due to summer baking and outdoor entertaining. "
            "2% milk is the top-selling dairy SKU."
        ),
        weather_forecast=(
            "Warm and dry next 14 days; highs 78–84°F; "
            "no precipitation forecast. Typical late-May Ohio pattern."
        ),
        unemployment_rate=(
            "Franklin County OH: 4.2% (Apr 2026), down 0.3pp YoY. "
            "Consumer confidence index 102 (stable). "
            "No major employer layoffs in the past 90 days."
        ),
    )

    workflow = DemandForecastWorkflow(config=config)
    result = await workflow.run(request=request)

    print(f"Converged: {result.converged} | Rounds: {result.rounds} | Score: {result.final_score:.1f}/10")
    print(f"Store: {result.metadata['store_id']} | SKU: {result.metadata['sku']}")
    print()
    print(result.output)
    print()
    print("--- Buyer Checklist ---")
    for item in result.metadata["buyer_checklist"]:
        print(item)
    if result.metadata["assumption_flags"]:
        print("\n--- Assumption Flags ---")
        for flag in result.metadata["assumption_flags"]:
            print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
