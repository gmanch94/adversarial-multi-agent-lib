"""
Supply-chain-resilience example — runs SupplyChainResilienceWorkflow on a
synthetic resilience review for an industrial OEM's IGBT-module commodity
following a Taiwan Strait scenario contingency review.

Triple-flag gate (SINGLE-SOURCE / GEO-CONCENTRATION / LEAD-TIME-FRAGILITY);
no veto.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.industrial.supply_chain_resilience
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.industrial.workflows.supply_chain_resilience import (
    SupplyChainResilienceRequest,
    SupplyChainResilienceWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = SupplyChainResilienceRequest(
        commodity_summary=(
            "IGBT modules (power-electronics commodity) — used on drive-unit "
            "motor-controller PCBAs across all lift-truck models. Annual spend "
            "$22.4M; ~80,000 modules/yr. Criticality: critical (no module → "
            "no truck). Current sourcing posture: dual-source at Tier-1 "
            "(Infineon + Mitsubishi)."
        ),
        tier1_supplier_map=(
            "Infineon: 60% share, allocated to high-volume models TR3600 + "
            "TR4800. Manufacturing: Dresden (DE) wafer fab + Kulim (MY) "
            "package + test. Mitsubishi: 40% share, allocated to TR2400 + "
            "automation product line. Manufacturing: Fukuoka (JP) wafer fab + "
            "Kuala Lumpur (MY) package + test. Active dual-source: yes — both "
            "suppliers receive scheduled orders; no paper-qualification."
        ),
        tier2_visibility=(
            "Wafer fabrication Tier-2: Infineon Dresden + TSMC Hsinchu (TW) "
            "(specialty trench-IGBT process; ~25% of Infineon volume) + GlobalFoundries "
            "Singapore. Mitsubishi: Fukuoka in-house wafer + TSMC Hsinchu "
            "(~30% of Mitsubishi volume — same TW fab as Infineon). "
            "**Hidden single-source via TSMC Hsinchu — both Tier-1 suppliers "
            "draw a material portion of their wafer supply from the same "
            "Taiwan fab.** Substrate (DBC ceramic): Curamik (DE) for Infineon, "
            "Rogers (US/JP) for Mitsubishi — distinct."
        ),
        geographic_context=(
            "Country exposure: Germany 35%, Japan 25%, Malaysia 20% (package/test), "
            "Taiwan 15% (wafer at Tier-2), Singapore 5%. Cluster: Hsinchu "
            "Science Park (TW) — both Tier-1 wafer suppliers; Kulim/KL (MY) "
            "package-and-test cluster. Political-risk: Taiwan Strait tension "
            "(elevated). Export-control: EAR ECCN 3A001.b.2 — license needed "
            "for select end-uses; ITAR not applicable. Natural-hazard: typhoon "
            "(TW + MY + JP), seismic (TW + JP), no water-stress flag."
        ),
        lead_time_and_route_context=(
            "Lead-time central tendency: Infineon 16 weeks (DE → US/EU/CN); "
            "Mitsubishi 18 weeks (JP/MY → US/EU/CN). Variance: ±3 weeks "
            "(CV ~18%). Recent disruption: Q3-2025 Suez delay added 2 weeks "
            "for EU-bound shipments. Route exposure: ocean primary; common "
            "chokepoints: Strait of Malacca (MY → US/EU), Suez (MY/JP → EU). "
            "Modal substitution: air-freight feasible at 4–5x cost premium; "
            "tested twice in 2024–2025 for surge. Port-of-entry diversity: "
            "Long Beach + Charleston + Hamburg + Rotterdam."
        ),
        inventory_and_buffer=(
            "Current strategic buffer: 6 weeks at OEM DCs (combined). Critical-"
            "spare cache: 0 (commodity, not single-spare class). Surge "
            "capacity: $2M air-freight authority pre-approved at VP-supply-chain. "
            "Recent buffer adjustments: +2 weeks after Q3-2025 Suez event."
        ),
        incident_or_trigger=(
            "Board-level contingency-planning review: Taiwan Strait scenario "
            "analysis. CFO requested supply-chain assessment of hidden Tier-2 "
            "Taiwan exposure across critical commodities. IGBT modules flagged "
            "as Tier-1-diverse but possibly Tier-2-concentrated."
        ),
    )

    workflow = SupplyChainResilienceWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Commodity: {result.metadata['commodity_summary'][:80]}...")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for label, key in [
        ("Single-Source Flags", "single_source_flags"),
        ("Geo-Concentration Flags", "geo_concentration_flags"),
        ("Lead-Time-Fragility Flags", "lead_time_fragility_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
