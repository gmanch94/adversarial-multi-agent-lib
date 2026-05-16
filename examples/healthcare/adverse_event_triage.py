"""
Adverse Event Triage — worked example (veto path).

Synthetic scenario: 68-year-old male patient receives amoxicillin 500mg for
a respiratory infection. Within 15 minutes of the first dose he develops
severe anaphylaxis (urticaria, angioedema, bronchospasm, hypotension requiring
epinephrine) and dies 6 hours later despite resuscitation. Fatal anaphylaxis
is unlabeled in the current USPI/SmPC per the sponsor safety database.
Causality is probable (WHO-UMC: strong temporal relationship, no alternative
cause, dechallenge not applicable due to fatal outcome).

The reviewer is expected to issue a REVIEWER VETO triggering the 7-day
expedited reporting clock under FDA 21 CFR 312 / EMA EudraVigilance / ICH E2A
(fatal unexpected ADR with causality ≥ possible).

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/healthcare/adverse_event_triage.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.healthcare.workflows.adverse_event_triage import (
    AdverseEventTriageWorkflow,
    AdverseEventRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/adverse-event-triage-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    # 68yo male — fatal anaphylaxis after amoxicillin first dose.
    # Unlabeled fatal outcome + causality probable → 7-day expedited clock.
    request = AdverseEventRequest(
        product_name="Amoxicillin 500mg capsules (Lot: AMX-2026-04812)",
        event_description=(
            "Patient developed severe anaphylaxis within 15 minutes of the first "
            "dose of amoxicillin: urticaria (diffuse), angioedema (face and larynx), "
            "bronchospasm (SpO2 dropped to 78%), and hypotension (BP 70/40 mmHg). "
            "Epinephrine 0.5mg IM administered x2 in ER. Despite resuscitation "
            "including IV fluids, vasopressors, and intubation, patient died 6 hours "
            "after event onset. Autopsy confirmed anaphylaxis as cause of death."
        ),
        patient_demographics=(
            "68-year-old male. Weight 82 kg. No prior allergy history documented "
            "in medical record. No previous amoxicillin or penicillin exposure noted. "
            "Medical history: hypertension, type 2 diabetes (well-controlled)."
        ),
        event_onset="2026-05-10 14:23 — within 15 minutes of first dose at 14:10",
        causality_assessment=(
            "Probable (WHO-UMC): strong temporal relationship (onset 15 min post-dose); "
            "dechallenge not applicable (fatal outcome); rechallenge not performed; "
            "no alternative cause identified (no other new drugs, no food allergen "
            "exposure, no insect sting); consistent mechanism (IgE-mediated "
            "penicillin hypersensitivity)."
        ),
        concomitant_medications=(
            "Lisinopril 10mg daily (stable x 2 years); "
            "Metformin 1000mg BID (stable x 3 years); "
            "No other new medications in past 30 days."
        ),
        outcome=(
            "Fatal — patient died 6 hours after anaphylaxis onset on 2026-05-10. "
            "Autopsy report confirms anaphylactic shock as primary cause of death."
        ),
        prior_reports=(
            "Anaphylaxis is listed in current USPI/SmPC as a known hypersensitivity "
            "reaction. HOWEVER: fatal anaphylaxis with this specific presentation "
            "(laryngeal angioedema + cardiovascular collapse in patient with no prior "
            "allergy history) is NOT listed as a labeled ADR in the current USPI/SmPC "
            "per sponsor safety database review dated 2026-05-11. Prior FAERS search "
            "returns 3 similar fatal anaphylaxis cases; none resulted in label update. "
            "Signal assessment pending."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = AdverseEventTriageWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running AdverseEventTriageWorkflow...")
    print(f"Product: {request.product_name}")
    print(f"Outcome: {request.outcome[:80]}...")
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
    print("ADVERSE EVENT CHECKLIST:")
    for item in result.metadata["adverse_event_checklist"]:
        print(f"  {item}")
    print()

    sev = result.metadata["severity_flags"]
    cau = result.metadata["causality_flags"]
    reg = result.metadata["regulatory_flags"]
    if sev or cau or reg:
        print(f"Severity flags ({len(sev)}): {sev}")
        print(f"Causality flags ({len(cau)}): {cau}")
        print(f"Regulatory flags ({len(reg)}): {reg}")


if __name__ == "__main__":
    asyncio.run(main())
