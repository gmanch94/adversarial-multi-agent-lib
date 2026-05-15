"""
ECO example — runs EngineeringChangeOrderWorkflow on a synthetic ECO impact
assessment for a drive-unit motor-controller PCBA component supersession
(IGBT module change driven by part obsolescence).

Triple-flag gate (SUPERSESSION / FMEA-DELTA / REGRESSION); no veto.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.industrial.engineering_change_order
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.industrial.workflows.engineering_change_order import (
    EngineeringChangeOrderRequest,
    EngineeringChangeOrderWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = EngineeringChangeOrderRequest(
        change_summary=(
            "ECO-26-0114 — Replace IGBT module Infineon FF300R12KT4 (obsolete "
            "EOL 2026-12) with Mitsubishi CM300DY-12NF on motor-controller PCBA "
            "P/N 8042-447. Reason: end-of-life; no last-time-buy capacity. "
            "Proposed effectivity: serial-effective from 8042-447 S/N >=240000. "
            "PCBA layout revision Rev D → Rev E (gate-driver rework + thermal-"
            "pad footprint change)."
        ),
        affected_part_numbers=(
            "8042-447 (PCBA assembly) Rev D → Rev E. 8042-447-IGBT (IGBT module "
            "sub-component) Infineon FF300R12KT4 → Mitsubishi CM300DY-12NF. "
            "Next-assembly: drive-unit assembly 8042-201 (used on lift-truck "
            "Models TR2400, TR3600). Service-parts catalog: existing service "
            "PCBA P/N 8042-447S — needs determination of supersession to new rev."
        ),
        f3_analysis=(
            "Originator-claimed F/F/F: form same (footprint identical to within "
            "0.4 mm), fit same (same mounting holes, same thermal-pad outline), "
            "function 'equivalent' (Vce-sat similar, Tj-max same, switching "
            "loss within 8%). Originator claims drop-in replacement. No mention "
            "of gate-driver compatibility delta; Mitsubishi gate-drive voltage "
            "+15/-9V vs Infineon +15/-8V."
        ),
        fmea_context=(
            "Current PFMEA for IGBT-module failure mode (over-temperature "
            "shutdown): severity 6, occurrence 2, detection 4, RPN 48. "
            "Current PFMEA for IGBT-module failure mode (latch-up under short-"
            "circuit): severity 9, occurrence 1, detection 3, RPN 27. "
            "Originator-proposed delta: no changes asserted."
        ),
        deployed_product_context=(
            "Field-installed population: ~42,000 lift trucks with PCBA 8042-447 "
            "Rev A–D. Firmware versions in use: FW-2.4 (12,000 units), FW-2.6 "
            "(18,000 units), FW-2.7 (12,000 units). Service-parts demand: ~340 "
            "PCBA / month replaced under warranty + paid service. Adjacent reuse: "
            "PCBA P/N 8042-447 is used only on drive-unit assembly 8042-201; "
            "not shared across other drive-unit families."
        ),
        supplier_and_tooling_context=(
            "Infineon: EOL announced Q3-2025, last-time-buy window closed "
            "Q1-2026. Mitsubishi: PPAP level 3, first-article approved 2026-01, "
            "capacity reservation 4,000 modules/month against expected 2,000 "
            "demand. Test-fixture change: new gate-drive voltage requires "
            "fixture firmware update (4-week lead). ICT and FCT test programs "
            "require new fault-coverage validation."
        ),
    )

    workflow = EngineeringChangeOrderWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Change: {result.metadata['change_summary'][:80]}...")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for label, key in [
        ("Supersession Flags", "supersession_flags"),
        ("FMEA-Delta Flags", "fmea_delta_flags"),
        ("Regression Flags", "regression_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
