"""
Inventory replenishment example — runs InventoryReplenishmentWorkflow
with a synthetic dairy / shelf-stable mix at a single DC.

Demonstrates the triple flag-gate pattern: reviewer challenges lead-time
realism, stockout projection, and DC + supplier capacity.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.retail.inventory_replenishment
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.retail.workflows.inventory_replenishment import (
    InventoryReplenishmentRequest,
    InventoryReplenishmentWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = InventoryReplenishmentRequest(
        dc_id="DC-DEN-014 (Denver mixing center)",
        sku_list=(
            "SKU-DAIRY-091 (private-label whole milk gallon): on-hand 9,800 cases, "
            "on-order 1,800 cases recv 2026-05-17. "
            "SKU-DAIRY-092 (private-label 2% gallon): on-hand 7,200 cases, "
            "on-order 1,200 cases recv 2026-05-17. "
            "SKU-SHELF-330 (private-label rolled oats 18oz): on-hand 14,400 cases, "
            "no on-order. "
            "SKU-SHELF-331 (private-label peanut butter 16oz): on-hand 5,600 cases, "
            "on-order 2,400 cases recv 2026-05-22."
        ),
        demand_forecast=(
            "DAIRY-091: 2,100 cases/wk central, ±15%. DAIRY-092: 1,600 cases/wk, "
            "±18%. SHELF-330: 1,250 cases/wk, ±10%. SHELF-331: 1,400 cases/wk, "
            "±12%. Source: DemandForecastWorkflow run 2026-05-13 weeks 21–24."
        ),
        lead_times=(
            "DAIRY supplier (FreshCo): quoted 3 days, p90 4 days, ship Mon/Wed/Fri. "
            "SHELF supplier (Heartland Grains): quoted 7 days, p90 9 days, ship Tue/Thu. "
            "SHELF supplier (NutriSpread): quoted 5 days, p90 6 days, ship Mon/Wed."
        ),
        safety_stock_policy=(
            "Safety stock = max(1.5σ over lead time, 5 days of forward demand) at "
            "p50 forecast. Dairy SKUs are safety-stock-critical (perishable, 21-day "
            "shelf life)."
        ),
        dc_capacity=(
            "Receiving: 240 pallet positions/day across 3 dock doors, 06:00–14:00 "
            "Mon–Sat. Closed Sun. Refrigerated receiving capped at 60 pallet "
            "positions/day for dairy. Overflow yard: 80 pallet positions (max 24h)."
        ),
        truck_economics=(
            "FTL break-even: 22 pallet positions per trailer for inland legs. Below "
            "that, LTL is cheaper. FTL fixed rate $1,400/leg; LTL ≈ $90/pallet."
        ),
        supplier_constraints=(
            "FreshCo: MOQ 600 cases (1 trailer), case pack 12, ship Mon/Wed/Fri. "
            "Heartland: MOQ 1,200 cases, case pack 24, ship Tue/Thu. "
            "NutriSpread: MOQ 800 cases, case pack 24, ship Mon/Wed."
        ),
    )

    workflow = InventoryReplenishmentWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"DC: {result.metadata['dc_id']}")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for kind in ("lead_time_flags", "stockout_flags", "capacity_flags"):
        flags = result.metadata.get(kind) or []
        if flags:
            print(f"\n--- {kind.replace('_', ' ').title()} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
