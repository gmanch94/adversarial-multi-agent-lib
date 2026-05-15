"""
Supplier-qualification example — runs SupplierQualificationWorkflow on a
synthetic re-qualification review for a hydraulic-component supplier
(Italy-based, single-region exposure).

Triple-flag gate (FINANCIAL / QUALITY / GEO-CONCENTRATION); no veto.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.industrial.supplier_qualification
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.industrial.workflows.supplier_qualification import (
    SupplierQualificationRequest,
    SupplierQualificationWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = SupplierQualificationRequest(
        supplier_summary=(
            "Idrotek SpA — hydraulic-cylinder + valve-block supplier; HQ + sole "
            "plant in Reggio Emilia, Italy. Commodity: hydraulic cylinders (3 SKU "
            "families) + valve blocks (2 SKU families) for lift-truck mast and "
            "drive systems. Proposed annual spend: $14.6M. Incumbency status: "
            "re-qualification (5-yr award expiring); current quality OK, financial "
            "noise prompted earlier review."
        ),
        financial_signals=(
            "FY2025 audited statements: revenue €68M (-4.2% YoY); EBITDA margin "
            "8.1% (down from 11.4%); net debt / EBITDA 3.4x (covenant 4.0x). "
            "DSO 84 days (industry median 62); inventory days 138 (industry 95). "
            "D&B Paydex 67 (slow-pay). RapidRatings FHR 38 (Caution tier). "
            "OEM is 22% of supplier revenue. Italian banking-group covenant "
            "review scheduled Q2-2026. No public M&A signal."
        ),
        quality_evidence=(
            "IATF 16949:2016 current — surveillance audit Sep-2025 closed with "
            "two minor findings. PPAP level 3 for incumbent parts; clean track "
            "record. SCAR history past 24 months: 3 issued, 3 closed within "
            "30 days. Escape rate 38 DPPM (vs OEM target ≤80). Two prior "
            "engineering escalations on burr-deburr step (root-caused, contained, "
            "PFMEA updated)."
        ),
        capacity_and_continuity=(
            "Single plant; sole machining + assembly line per cylinder family. "
            "BCP/DRP last revised 2022 — pre-COVID; no fire-and-flood drill "
            "documented. Insurance: €40M property + €25M business-interruption "
            "(carrier financial strength A.M. Best A). Backup-tooling: secondary "
            "machining at Reggio plant; no offsite. Capacity reservation for "
            "OEM: 24,000 cylinders/yr (current run-rate 21,300)."
        ),
        sub_tier_and_geographic=(
            "Tier-2 steel-tube supply: 60% Italy (Brescia cluster), 30% Germany "
            "(Bayern), 10% Czech Republic. Magnet-array sensor (in valve block): "
            "100% single Tier-2 in Shenzhen, China (same Tier-2 supplies two of "
            "OEM's other Tier-1s — hidden single-source exposure). EU sanctions / "
            "export-control screen clean (Italian entity, no Russia ties post-"
            "2022). Natural-hazard overlay: low seismic at Reggio; low water-"
            "stress; cluster shares Po-valley logistics with multiple OEM Tier-1s."
        ),
        proposed_qualification=(
            "Procurement engineer recommends Conditionally Qualified with three "
            "conditions: (1) quarterly financial-stress monitoring tied to "
            "RapidRatings FHR ≥40 trigger; (2) updated BCP/DRP with fire-drill "
            "evidence by Q3-2026; (3) accelerate dual-source qualification for "
            "the magnet-array sensor at the Tier-2 level."
        ),
    )

    workflow = SupplierQualificationWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Supplier: {result.metadata['supplier_summary'][:80]}...")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for label, key in [
        ("Financial Flags", "financial_flags"),
        ("Quality Flags", "quality_flags"),
        ("Geo-Concentration Flags", "geo_concentration_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
