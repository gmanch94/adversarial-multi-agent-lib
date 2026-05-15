"""
Product-liability example — runs ProductLiabilityRootCauseWorkflow on a
synthetic pedestrian-strike incident attribution where initial draft
attributes to operator error but telematics evidence suggests a design-
defect signal (geofence interlock failure).

Veto + triple-flag gate (DESIGN-DEFECT / OPERATOR-ERROR / WARNING-ADEQUACY).

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.industrial.product_liability_root_cause
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.industrial.workflows.product_liability_root_cause import (
    ProductLiabilityRootCauseRequest,
    ProductLiabilityRootCauseWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = ProductLiabilityRootCauseRequest(
        incident_summary=(
            "2026-02-22 — Pedestrian-strike incident at Memphis TN beverage "
            "distribution facility. Lift-truck Model TR3600 serial TR3600-2024-"
            "10277 struck warehouse pedestrian in mixed-traffic aisle. "
            "Pedestrian: bilateral lower-leg fracture, partial permanent "
            "disability (catastrophic-tier per OEM internal criteria). "
            "Equipment impounded; OEM investigation initiated under cooperation "
            "agreement with customer-side counsel. Chain-of-custody: OEM "
            "service-engineering took possession 2026-02-25."
        ),
        telematics_and_trace=(
            "InfoLink telemetry: 14-second window pre-impact. Throttle input "
            "62% (consistent with normal aisle travel). Speed at impact "
            "8.4 km/h (above 4 km/h aisle geofence limit). "
            "Geofence-zone-active flag: TRUE — geofence boundary was active. "
            "Speed-limiter-engaged flag: FALSE — interlock did not engage. "
            "Event-data-recorder shows operator-presence-sensor active throughout. "
            "Video: facility camera shows pedestrian entering aisle 1.8 s before "
            "impact; operator turned head 0.4 s before impact. No braking input."
        ),
        equipment_configuration=(
            "Model TR3600 with optional zone-control geofencing (P/N 8044-201 "
            "geofence module installed). Build date 2024-10-14. ECOs applied: "
            "ECO-25-0088 (geofence firmware FW-1.7 → FW-1.8) applied 2025-08-12. "
            "Recent service: 2026-01-04 (250-hr service, no fault codes recorded). "
            "Hours at incident: 1,420."
        ),
        standards_context=(
            "Applicable: ANSI/ITSDF B56.1-2020 (Powered Industrial Trucks, "
            "Low- and High-Lift). OSHA 1910.178 (operator training, "
            "pedestrian-strike hazard). ITSDF Best Practice — zone control / "
            "geofence interlock per B56.11.6-2018 (Hand-Held / Operator-Up). "
            "EU 3691-1 not applicable (US-only deployment)."
        ),
        operator_and_training=(
            "Operator: 4-year tenure at customer; OSHA-compliant initial training "
            "+ annual refresher; certificate current. Trained on TR3600 model "
            "specifically. Customer's site-specific training emphasises 'sound "
            "horn at aisle intersections' (operator did not, per video). "
            "Operator declined post-incident statement on counsel advice."
        ),
        field_failure_population=(
            "Population query against InfoLink telematics for Model TR3600 with "
            "geofence module 8044-201, firmware FW-1.8: 6,400 units deployed. "
            "Reports of 'speed-limiter did not engage in geofence zone': 14 "
            "incidents in past 12 months (vs prior 12-month total of 2 on FW-1.7). "
            "All 14 incidents post-date ECO-25-0088 FW-1.8 release. No prior "
            "pedestrian-strike with injury reported."
        ),
        initial_attribution=(
            "Investigator's first-pass: operator-error (failure to sound horn, "
            "failure to slow at aisle intersection per site rules). Operator "
            "training-of-record adequate; warnings present; horn functional. "
            "Recommend defence position: operator-error, no design contribution."
        ),
    )

    workflow = ProductLiabilityRootCauseWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Incident: {result.metadata['incident_summary'][:80]}...")
    print(f"Vetoed: {result.metadata.get('vetoed', False)}")
    if result.metadata.get("vetoed"):
        print(f"Veto reason: {result.metadata['veto_reason']}")
    print()
    print(result.output)
    print()
    print("--- Safety Checklist ---")
    for item in result.metadata["safety_checklist"]:
        print(item)
    for label, key in [
        ("Design-Defect Flags", "design_defect_flags"),
        ("Operator-Error Flags", "operator_error_flags"),
        ("Warning-Adequacy Flags", "warning_adequacy_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
