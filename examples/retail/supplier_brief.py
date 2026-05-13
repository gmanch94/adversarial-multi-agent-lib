"""
Supplier negotiation brief example — runs SupplierBriefWorkflow with a
synthetic packaging-supplier renegotiation scenario.

Demonstrates the triple flag-gate pattern: reviewer challenges BATNA
strength, cost-floor defence, and relationship implications.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.retail.supplier_brief
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.retail.workflows.supplier_brief import (
    SupplierBriefRequest,
    SupplierBriefWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = SupplierBriefRequest(
        supplier_name="Pacific Corrugated Co. (anonymised)",
        category="corrugated-packaging (mid-size shipper boxes, RSC-32ECT)",
        current_terms=(
            "Price: $0.84 / shipper box. Payment: net-45. MOQ: 50,000 boxes / "
            "release. Lead time: 18 days. 36-month agreement, 14 months remaining."
        ),
        target_terms=(
            "Price: $0.78 / box (-7.1%). Payment: net-60. MOQ: 75,000 / release. "
            "Lead time: 14 days. Extend agreement by 24 months at new terms."
        ),
        volume_history=(
            "Trailing 12 months: 4.8M boxes, +6% YoY. Forecast next 12 months: "
            "5.1M boxes (+6%). Pacific is currently sole-source for this SKU."
        ),
        alternatives=(
            "Midwest Box Inc. — qualified, +4% landed cost vs Pacific, audited "
            "Q3 2025, capacity ~3.2M boxes/yr (would cover ~63% of volume). "
            "RegionalPak — not yet qualified, indicative quote -2% vs Pacific, "
            "audit cycle ~4 months."
        ),
        cost_drivers=(
            "Containerboard index (corporate procurement feed, 2026-04 print): "
            "-3.4% YoY. Inland freight diesel index: +1.1% YoY. Labour at "
            "Pacific's plant: estimated +2.5% YoY based on regional CBA data."
        ),
        relationship_context=(
            "Pacific is a STRATEGIC supplier — sole-source on this SKU plus two "
            "co-developed sustainable-fibre SKUs not in scope here. Joint "
            "innovation roadmap signed 2024. Multi-year priority allocation "
            "during 2024 supply crunch was meaningful."
        ),
        negotiation_constraints=(
            "ESG: Pacific is a Tier-1 sustainability partner; any volume shift "
            "away counts against corporate Scope-3 reduction roadmap. "
            "Compliance: payment-term changes beyond net-60 require CFO "
            "approval. Procurement policy: walk-away on a sole-source SKU "
            "requires 90-day continuity plan."
        ),
    )

    workflow = SupplierBriefWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(
        f"Supplier: {result.metadata['supplier_name']} | "
        f"Category: {result.metadata['category']}"
    )
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for kind in ("batna_flags", "cost_flags", "relationship_flags"):
        flags = result.metadata.get(kind) or []
        if flags:
            print(f"\n--- {kind.replace('_', ' ').title()} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
