"""
Labor Scheduling example — runs LaborSchedulingWorkflow with synthetic Kroger data.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.retail.labor_scheduling
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.retail.workflows.labor_scheduling import (
    LaborSchedulingWorkflow,
    SchedulingRequest,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = SchedulingRequest(
        store_id="KRO-OH-0042",
        week_start="2026-05-18",
        projected_traffic=(
            "Mon: 1,200 customers; Tue: 1,100; Wed: 1,150; Thu: 1,300; "
            "Fri: 1,800 (peak 5–7pm); Sat: 2,400 (peak 11am–2pm); Sun: 1,600. "
            "Busiest day: Saturday due to high school graduation in the area."
        ),
        staff_roster=(
            "Alice Chen — cashier, FT (40h/wk), available all 7 days; "
            "Bob Torres — cashier, PT (20h/wk), unavailable Friday; "
            "Carol Singh — produce specialist, FT, available all 7 days; "
            "Dave Kim — overnight stocker, PT (32h/wk), available Mon–Thu only; "
            "Eve Johnson — store manager, FT, available all 7 days"
        ),
        labor_budget="$4,200 for the week (including all wages and benefits est.)",
        local_events=(
            "Jefferson High School graduation ceremony Saturday 10am–12pm, "
            "held 0.3 miles from store. Expect elevated Sat AM traffic. "
            "No other scheduled events this week."
        ),
        state_labor_law_notes=(
            "Ohio (18+ employees): "
            "OT rate 1.5x applies to all hours over 40/week; "
            "30-minute unpaid break required for any shift exceeding 6 hours; "
            "no minor labor restrictions (all staff are 18+); "
            "minimum wage $10.45/hr (all staff above this rate)"
        ),
        unemployment_rate=(
            "Franklin County OH: 4.2% (Apr 2026), down 0.3pp YoY. "
            "Retail sector hiring is competitive; two new stores opened in the trade area Q1. "
            "PT staff turnover risk: moderate."
        ),
    )

    workflow = LaborSchedulingWorkflow(config=config)
    result = await workflow.run(request=request)

    print(f"Converged: {result.converged} | Rounds: {result.rounds} | Score: {result.final_score:.1f}/10")
    print(f"Store: {result.metadata['store_id']} | Week: {result.metadata['week_start']}")
    print()
    print(result.output)
    print()
    print("--- Manager Checklist ---")
    for item in result.metadata["manager_checklist"]:
        print(item)
    if result.metadata["compliance_flags"]:
        print("\n--- Compliance Flags ---")
        for flag in result.metadata["compliance_flags"]:
            print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
