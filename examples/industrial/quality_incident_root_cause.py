"""
Quality-incident-root-cause example — runs QualityIncidentRootCauseWorkflow
on a synthetic 8D investigation for a hydraulic-cylinder seal failure
that escaped to field on a lift-truck mast assembly.

Triple-flag gate (CAUSAL-CHAIN / CONTAINMENT / SYSTEMIC); no veto.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.industrial.quality_incident_root_cause
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.industrial.workflows.quality_incident_root_cause import (
    QualityIncidentRootCauseRequest,
    QualityIncidentRootCauseWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = QualityIncidentRootCauseRequest(
        incident_summary=(
            "2026-03-12 — Customer-site failure: lift-truck Model TR2400 serial "
            "TR2400-2025-04188 (Memphis TN distribution center). Mast hydraulic "
            "cylinder lower-seal extrusion at 1,840 hours operation. Detected by "
            "operator (oil pool); no injury, no load drop. Failure mode: outer "
            "static seal extruded past gland, lost ~340 mL hydraulic oil. "
            "Equipment returned to OEM service center."
        ),
        evidence_inventory=(
            "Failed seal teardown: outer static seal showed gland-edge extrusion "
            "on the pressure side, no chemical degradation, durometer in spec. "
            "Gland surface: machining-tool-line burr (0.06 mm) on the load-side "
            "edge — outside drawing-spec 0.02 mm Ra. SPC chart for gland-OD "
            "machining op shows 8 of 30 recent units exceeded Ra spec — process "
            "drift. Traceability: failed cylinder built 2024-11-04, Italy plant. "
            "MSA on gland-OD profilometer: GR&R 22% (acceptable per AIAG). No "
            "witness statement (unattended failure)."
        ),
        initial_causal_hypothesis=(
            "Investigator's first-pass: gland-OD burr from worn machining tool "
            "(due-replacement at 800 cycles, replaced at 1,150 cycles). "
            "Operator did not catch out-of-spec parts because gauge-inspection "
            "moved from 100% to AQL sampling in Q3-2024."
        ),
        containment_scope=(
            "Containment to date: in-plant WIP (840 cylinders) — 100% inspected, "
            "29 over Ra spec, segregated. Finished goods at Italy plant (560) — "
            "100% inspected, 18 over spec. In-transit to OEM DCs (1,140) — "
            "sample-inspected 200 units, 5 over spec; remaining un-inspected. "
            "OEM DC stock (2,300) — not inspected. In-service field-deployed "
            "(~14,200 cylinders built since 2024-09 tool-change-control degraded) "
            "— not addressed; sort method not yet determined."
        ),
        process_and_design_context=(
            "Current PFMEA row for this failure mode: severity 7 (loss of "
            "function + oil release), occurrence 2 (rare), detection 3 "
            "(100% in-process gauge → since Q3 2024 changed to AQL). Current "
            "RPN 42; pre-change RPN was 14. Drawing spec: gland-OD Ra ≤0.02 mm; "
            "tool-life specified 800 cycles. SPC reaction-plan: did not trigger "
            "(individual-value chart, not running-average)."
        ),
        adjacent_products=(
            "Model TR2400 mast uses this cylinder series exclusively. Adjacent "
            "lift-truck models TR3600 + TR4800 use a different cylinder family "
            "machined on a different line — not impacted. Adjacent applications "
            "(scissor-lift OEM customers) buy similar gland geometry from same "
            "Italy plant — same machining line, same tool-control regime."
        ),
    )

    workflow = QualityIncidentRootCauseWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Incident: {result.metadata['incident_summary'][:80]}...")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for label, key in [
        ("Causal-Chain Flags", "causal_chain_flags"),
        ("Containment Flags", "containment_flags"),
        ("Systemic Flags", "systemic_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
