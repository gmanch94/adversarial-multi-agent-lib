"""
Recall-scope example — runs RecallScopeManufacturingWorkflow on a synthetic
recall-scope determination for a lift-truck geofence-interlock firmware
defect (FW-1.8) where pedestrian-strike risk has emerged in the field.

Veto + triple-flag gate (TRIGGER-EVIDENCE / FLEET-SCOPE / REGULATORY-NOTIFY).

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.industrial.recall_scope_manufacturing
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.industrial.workflows.recall_scope_manufacturing import (
    RecallScopeManufacturingRequest,
    RecallScopeManufacturingWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = RecallScopeManufacturingRequest(
        trigger_summary=(
            "Trigger: geofence-zone speed-limiter interlock fails to engage on "
            "Model TR3600 lift-trucks running firmware FW-1.8 (released via "
            "ECO-25-0088, 2025-08). 14 in-zone speed-limiter non-engagement "
            "incidents in past 12 months (vs 2 on prior FW-1.7). One incident "
            "(2026-02-22 Memphis TN) escalated to pedestrian-strike with "
            "partial permanent disability. CPSC § 15(b) tier hypothesis: "
            "Tier 1 (serious injury occurred) AND Tier 2 (unreasonable risk to "
            "operators / pedestrians in mixed-traffic facilities)."
        ),
        evidence_inventory=(
            "InfoLink telematics: 14 in-zone non-engagement events confirmed "
            "by geofence-state-vs-speed-limiter-state correlation. Engineering "
            "investigation: FW-1.8 race condition in geofence-state-handler "
            "when zone-boundary crossed during throttle-input transient — "
            "interlock engagement command issued but not honoured by motor-"
            "controller-PCBA state machine. Root cause confirmed by bench "
            "reproduction on 4 units. No telematics gap. Customer complaints: "
            "27 in past 12 months mentioning 'truck didn't slow in zone'."
        ),
        fleet_serial_traceability=(
            "Model TR3600 with geofence module 8044-201 firmware FW-1.8: "
            "6,400 units deployed. Build dates 2025-08-12 (ECO release) through "
            "present. Serials: TR3600-2025-09xxx through current 2026-04xxx. "
            "Configurations: all geofence-equipped variants (option pack OPT-GF1, "
            "OPT-GF2). Pre-production / engineering builds: 12 internal units. "
            "International: 1,840 units in EU (Germany, France, Italy, NL); "
            "320 units in Canada; remainder US."
        ),
        adjacent_product_exposure=(
            "Models TR2400 + TR4800 use a different geofence module (P/N 8044-403) "
            "with separate firmware family — NOT affected. Model TR3600 variants "
            "without geofence option are NOT affected. Service-parts catalog: "
            "single replacement firmware P/N FW-1.8-A used only on this model + "
            "option. AGV/AMR product line uses different platform — not affected."
        ),
        regulatory_context=(
            "US: CPSC § 15(b) reportable (Tier 1 serious-injury + Tier 2 "
            "unreasonable risk); 5-business-day clock from 2026-02-22 "
            "(date OEM 'became aware'). OSHA: workplace-incident reportable at "
            "the customer; OSHA inquiry not yet opened. NHTSA-equivalent: "
            "N/A (off-road industrial truck). EU: GPSR Article 5 Safety Gate "
            "notification required for the 1,840 EU units; per-member-state "
            "market-surveillance notification (DE, FR, IT, NL). Canada: CCPSA "
            "notification required (320 units). No state AG inquiry."
        ),
        service_capacity_context=(
            "Remediation: firmware update FW-1.8 → FW-1.9 (race-condition fix); "
            "OTA-capable via InfoLink for 4,800 of 6,400 units; remaining 1,600 "
            "require service-technician visit. Service-network capacity: 28-day "
            "rolling window can absorb ~2,400 dispatch visits at current load. "
            "Parts: no physical parts required. Customer-facing communications: "
            "drafted; customer-service phone-bank scaled."
        ),
        proposed_scope=(
            "Initial scope: all 6,400 TR3600 + geofence + FW-1.8 units globally. "
            "Action: mandatory firmware update to FW-1.9; operator-instruction "
            "to maintain manual aisle-speed discipline until updated. CPSC § "
            "15(b) report drafted with attached field-failure data. Reinsurer "
            "notification: above product-liability retention; treaty notice "
            "drafted. Customer-communication: dealer-cascade + direct-mail."
        ),
    )

    workflow = RecallScopeManufacturingWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Trigger: {result.metadata['trigger_summary'][:80]}...")
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
        ("Trigger-Evidence Flags", "trigger_evidence_flags"),
        ("Fleet-Scope Flags", "fleet_scope_flags"),
        ("Regulatory-Notify Flags", "regulatory_notify_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
