"""
Drug Interaction Flagging — worked example (veto path).

Synthetic scenario: 72-year-old CKD3 patient on warfarin, metoprolol, and
lisinopril. Prescriber requests ibuprofen for an osteoarthritis flare.
The warfarin + NSAID combination is a narrow-therapeutic-index interaction
with high bleed risk; the reviewer is expected to issue a REVIEWER VETO.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/healthcare/drug_interaction_flagging.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.healthcare.workflows.drug_interaction_flagging import (
    DrugInteractionFlaggingWorkflow,
    DrugInteractionRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/drug-interaction-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    # 72yo CKD3 patient on warfarin + metoprolol + lisinopril.
    # New NSAID request: demonstrates likely veto on warfarin + NSAID NTI interaction.
    request = DrugInteractionRequest(
        patient_id="PT-EXAMPLE-001",
        medication_list=(
            "warfarin 5mg daily (INR target 2.0-3.0, last INR 2.4 one week ago); "
            "metoprolol succinate 50mg daily; "
            "lisinopril 10mg daily"
        ),
        new_medication="ibuprofen 600mg q6h prn (requested for osteoarthritis flare, left knee)",
        indication="Osteoarthritis pain flare, left knee. Patient reports 7/10 pain. "
                   "Acetaminophen 1g TID tried for 2 weeks without adequate relief.",
        renal_function="eGFR 52 mL/min/1.73m2 (CKD stage 3a, stable x 18 months)",
        hepatic_function="ALT 28 U/L, AST 31 U/L, bilirubin 0.8 mg/dL — within normal limits. "
                         "No cirrhosis. Child-Pugh A.",
        allergy_history="Penicillin — rash (documented). No documented NSAID allergy.",
        formulary_reference=(
            "Lexicomp drug interaction monograph: warfarin + ibuprofen — MAJOR. "
            "NSAIDs inhibit platelet aggregation and may cause GI mucosal injury; "
            "concurrent use increases INR and bleeding risk 3-7 fold. "
            "Avoid combination; if NSAID required, use lowest effective dose with "
            "intensive INR monitoring and GI prophylaxis. "
            "Lisinopril + ibuprofen — MODERATE. NSAIDs may attenuate ACEi "
            "antihypertensive effect and worsen renal function. "
            "Micromedex: NSAIDs in CKD eGFR < 60 — caution; may precipitate AKI."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = DrugInteractionFlaggingWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running DrugInteractionFlaggingWorkflow...")
    print(f"Patient: {request.patient_id}")
    print(f"New medication: {request.new_medication[:60]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()

    if result.metadata.get("vetoed"):
        print("*** REVIEWER VETO ISSUED ***")
        print(f"Veto reason: {result.metadata['veto_reason']}")
        print()

    print("OUTPUT:")
    print(result.output)
    print()
    print("INTERACTION CHECKLIST:")
    for item in result.metadata["interaction_checklist"]:
        print(f"  {item}")
    print()

    sev = result.metadata["severity_flags"]
    evi = result.metadata["evidence_flags"]
    con = result.metadata["contraindication_flags"]
    if sev or evi or con:
        print(f"Severity flags ({len(sev)}): {sev}")
        print(f"Evidence flags ({len(evi)}): {evi}")
        print(f"Contraindication flags ({len(con)}): {con}")


if __name__ == "__main__":
    asyncio.run(main())
