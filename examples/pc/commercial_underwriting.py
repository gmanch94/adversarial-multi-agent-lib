"""
Commercial-underwriting example — runs CommercialUnderwritingWorkflow on a
synthetic mid-market manufacturer submission (metal fabrication with hot-work
exposure, $48M revenue, hazardous-class GL bind).

Triple-flag gate (LOSS-COST / EXCLUSION / CAPACITY); no veto.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.pc.commercial_underwriting
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.pc.workflows.commercial_underwriting import (
    CommercialUnderwritingRequest,
    CommercialUnderwritingWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = CommercialUnderwritingRequest(
        insured_summary=(
            "Ironclad Fabrication LLC — custom structural-steel fabricator, "
            "NAICS 332312 (Fabricated Structural Metal Manufacturing). "
            "Headquarters: Erie, PA; one production facility (74,000 sq.ft.). "
            "Annual revenue: $48.2M (2025). Employee count: 122. "
            "Operations: precision-cut, weld, finish structural members and "
            "stairs/railings for commercial construction; ~30% of work performed "
            "at customer sites (installation crews)."
        ),
        prior_loss_history=(
            "5-year GL loss runs: $1.42M total incurred across 7 claims. "
            "Two claims > $250k: 2023 hot-work fire at customer site ($580k; "
            "subcontractor scope dispute); 2024 falling-object injury at customer "
            "site ($315k). Frequency stable at ~1.4 claims/yr. Severity trend "
            "rising (large-loss tail is the concern)."
        ),
        hazard_grade=(
            "Hazard tier: HIGH. Special hazards: hot work (welding, cutting, "
            "grinding) at customer sites; falling-object exposure during install; "
            "structural-fit liability (post-completed-operations)."
        ),
        requested_coverage=(
            "GL: $1M/$2M per-occurrence/aggregate; products-completed-operations "
            "$2M aggregate. Property: $14M building+contents. Auto: fleet of 18 "
            "vehicles, $1M CSL. Umbrella: $10M over GL+Auto+EL. EL via WC carrier."
        ),
        proposed_terms=(
            "GL: $1M/$2M; per-occurrence $1M. Deductible: $25k SIR per GL claim. "
            "Premium: $96,500 (GL); $14,800 (GL umbrella attach point). "
            "Scheduled endorsements: contractors limitation, additional-insured-blanket, "
            "primary-and-noncontributory. No designated-premises restriction proposed."
        ),
        regulatory_context=(
            "Admitted in PA, OH, WV, NY (customer-site territories). Filed ISO program "
            "with company LCM = 1.18. Filed deviation: ±10% available for "
            "frequency-credit / debit. Surplus-lines stamp not required at proposed "
            "limits. State filings up to date."
        ),
        capacity_constraint=(
            "LOB aggregate (manufacturing GL): $42M of $50M cap used. This bind would "
            "use $2M, fits within cap. Treaty cession: per-risk net retention $1M, "
            "treaty layer $4M xs $1M — within net retention. Cat-zone: not material "
            "for GL. No reinsurer-specific approval required at $1M/$2M."
        ),
    )

    workflow = CommercialUnderwritingWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Insured: {result.metadata['insured_summary'][:80]}...")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for label, key in [
        ("Loss-Cost Flags", "loss_cost_flags"),
        ("Exclusion Flags", "exclusion_flags"),
        ("Capacity Flags", "capacity_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
