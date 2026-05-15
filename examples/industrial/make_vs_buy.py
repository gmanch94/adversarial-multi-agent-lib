"""
Make-vs-buy example — runs MakeVsBuyWorkflow on a synthetic decision for an
electric-motor controller PCBA at an industrial lift-truck OEM. Decision frame:
in-house China-2 plant SMT line vs Tier-1 EMS in Vietnam.

Triple-flag gate (COST / CAPABILITY / IP-LEAK); no veto.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.industrial.make_vs_buy
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.industrial.workflows.make_vs_buy import (
    MakeVsBuyRequest,
    MakeVsBuyWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = MakeVsBuyRequest(
        component_summary=(
            "Drive-unit motor-controller PCBA, P/N 8042-447. Annual demand 24,000 "
            "units across two lift-truck models. Design owned by OEM (proprietary "
            "field-oriented-control firmware). Sub-assembly map: feeds 4 final-"
            "assembly stations across NA + EU plants."
        ),
        internal_cost_basis=(
            "Should-cost build-up (China-2 SMT line): direct material $48.20 "
            "(LME-indexed copper + qualified IGBT module + passives at Tier-1 "
            "distributor); direct labour $4.10 (0.18 hr × $22.80/hr loaded); "
            "overhead $8.40 (machine-hour basis at 28% line utilisation); capex "
            "amortisation $3.10 (existing SMT line, residual amortisation 2.5 yrs); "
            "capacity-opportunity cost: line currently 28% utilised — alternative "
            "work would not displace; quality + warranty reserve $1.80. "
            "TOTAL should-cost $65.60/unit. ±15% sensitivity on copper + IGBT."
        ),
        external_bid_summary=(
            "Two normalised bids (DDP-China-2-plant, OEM annual demand): "
            "Vietnam Tier-1 EMS (Bid A): $52.80/unit landed; MOQ 5,000; 16-week "
            "lead-time; tooling $180k amortised over 3 yrs. Mexico Tier-1 EMS "
            "(Bid B): $58.40/unit landed; MOQ 2,500; 8-week lead-time; tooling "
            "$220k amortised over 3 yrs. Bid A delta vs should-cost: -$12.80 "
            "year-1, -$11.40 steady-state (incl. tooling amort)."
        ),
        capability_evidence=(
            "In-house: PPAP level 3 demonstrated on similar PCBA P/N 8042-388; "
            "Cpk 1.67 on critical solder-joint integrity; PFMEA refreshed Q4-2025; "
            "fixture validation complete. Engineering bandwidth: 1.5 FTE DRE "
            "available for transition. "
            "Vietnam Tier-1: PPAP level 2 with 18-month track record on adjacent "
            "PCBA programs (different OEM); first-article approved Q3-2025; "
            "SCAR-history 4 in past 18 months (2 systemic, closed). "
            "Mexico Tier-1: PPAP level 3 on this PCBA from a prior award (3-yr "
            "track record); no SCAR-history; fixture and first-article current."
        ),
        ip_risk_context=(
            "IP at risk: proprietary field-oriented-control firmware loaded at "
            "test station + magnet-array pattern on integrated motor sensor. "
            "Vietnam Tier-1: factory shares industrial park with two competitor "
            "OEMs; firmware loaded via test-fixture image (no source-code "
            "exposure); EAR ECCN 3A001.b.2 — verify export-control license for "
            "magnet-array; counterfeit-control history clean. "
            "Mexico Tier-1: dedicated cell for this OEM; firmware and fixture "
            "managed by OEM-supplied test rig; no industrial-park sharing concern."
        ),
        strategic_constraints=(
            "Capacity reservation: in-house China-2 line could accommodate 32,000 "
            "units/yr if expanded. Vietnam Tier-1 capacity reservation: 30,000 "
            "units/yr available. Mexico Tier-1 capacity reservation: 24,000 / yr "
            "available. Exit-cost tolerance: 12 months notice acceptable. Long-"
            "term contract horizon: 3-year initial term with annual renewal."
        ),
    )

    workflow = MakeVsBuyWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Component: {result.metadata['component_summary'][:80]}...")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for label, key in [
        ("Cost Flags", "cost_flags"),
        ("Capability Flags", "capability_flags"),
        ("IP-Leak Flags", "ip_leak_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
