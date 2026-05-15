"""
Telematics-anomaly-triage example — runs TelematicsAnomalyTriageWorkflow on
a synthetic InfoLink-class anomaly alert (battery-pack thermal anomaly on
a lift-truck deployed at a refrigerated-warehouse customer).

Triple-flag gate (SIGNAL-EVIDENCE / FALSE-POSITIVE-COST / ACTIONABILITY);
no veto.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.industrial.telematics_anomaly_triage
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.industrial.workflows.telematics_anomaly_triage import (
    TelematicsAnomalyTriageRequest,
    TelematicsAnomalyTriageWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = TelematicsAnomalyTriageRequest(
        asset_summary=(
            "Asset: Lift-truck Model TR2400 Class-1 electric, serial TR2400-2024-"
            "08812. Customer: ColdLink Logistics — refrigerated-warehouse "
            "operation (Dallas TX). Equipment age: 18 months. Battery: lithium-"
            "ion 80V / 600Ah, factory-installed."
        ),
        signal_payload=(
            "Anomaly: battery-pack thermal sensor T-cell-7 reported 51.4 °C "
            "during 2026-04-29 02:14 UTC (15-minute sustained reading). "
            "Detector threshold for warn-tier: 48.0 °C; alarm-tier 55.0 °C. "
            "Deviation from this asset's 90-day baseline: +12 °C above the "
            "P95 baseline of 39.4 °C; +4.2σ. Detector confidence: 0.83 "
            "(calibrated). Corroborating signals: cell-7 internal resistance "
            "increase +18% over 30 days (gradual). No other thermal sensors "
            "above warn-tier in this pack. Single sustained event (not "
            "repeated)."
        ),
        duty_cycle_baseline=(
            "30-day duty cycle: 14.2 hrs/day operation (heavy-duty); 4.1 cycles/"
            "hour pallet-pick load profile. Digital-twin baseline for this "
            "asset shows pack thermal P95 39.4 °C (this signal 12 °C above)."
        ),
        recent_service_history=(
            "Recent service: 2026-04-12 (1,000-hr service, no thermal events "
            "noted); 2025-11-04 (battery-management firmware update FW-3.1 → "
            "FW-3.2 — no known regressions). No prior cell-7 alerts. Battery "
            "warranty: 4 years (active)."
        ),
        customer_contract_context=(
            "Customer SLA: 4-hour response on thermal-tier alarms; 24-hour "
            "response on thermal-tier warnings. Customer has 3 spare lift-"
            "trucks on-site; downtime tolerance moderate. Prior incident "
            "posture: 1 unrelated dispatch in past 12 months (drive-unit "
            "noise — resolved)."
        ),
        parts_and_service_network=(
            "Candidate parts: replacement BMS cell-monitoring board ($420; "
            "Dallas DC has 4 in stock); replacement cell module ($1,180; "
            "Houston DC has 2; 24-hour transit). Service-network: Dallas "
            "service-cell has 2 certified battery technicians; capacity "
            "available within 4-hour SLA."
        ),
        initial_recommendation=(
            "Service-engineer first-pass: dispatch within 24-hour SLA window "
            "for cell-7 diagnostic; bring BMS cell-monitoring board and one "
            "cell-module spare. Trigger upgraded if internal-resistance trend "
            "continues."
        ),
    )

    workflow = TelematicsAnomalyTriageWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Asset: {result.metadata['asset_summary'][:80]}...")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for label, key in [
        ("Signal-Evidence Flags", "signal_evidence_flags"),
        ("False-Positive-Cost Flags", "false_positive_cost_flags"),
        ("Actionability Flags", "actionability_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
