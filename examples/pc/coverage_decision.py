"""
Coverage / bad-faith example — runs CoverageDecisionWorkflow on a synthetic
business-interruption coverage dispute (restaurant insured, civil-authority
order, virus-exclusion question).

Demonstrates the reviewer-veto pattern (D-PC-4): bad-faith exposure on a
proposed denial halts the loop regardless of score.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.pc.coverage_decision
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.pc.workflows.coverage_decision import (
    CoverageDecisionRequest,
    CoverageDecisionWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = CoverageDecisionRequest(
        claim_summary=(
            "Insured: Apex Bistro LLC (independent restaurant, Hamilton County OH). "
            "Claim filed 2026-03-04 for business-interruption losses 2026-02-12 through "
            "2026-02-28 (16 days). Cause: county health-department closure order following "
            "norovirus cluster traced to insured's premises. Claimed BI loss: $187,500 "
            "(per insured's interim P&L)."
        ),
        policy_wording=(
            "Form CP 00 30 10 12 (Business Income (and Extra Expense) Coverage). "
            "Insuring agreement: 'We will pay for the actual loss of Business Income you "
            "sustain due to the necessary suspension of your operations during the period "
            "of restoration. The suspension must be caused by direct physical loss of or "
            "damage to property at premises described in the Declarations.' "
            "Endorsement CP 01 40 07 06 (Exclusion of Loss Due to Virus or Bacteria): "
            "'We will not pay for loss or damage caused by or resulting from any virus, "
            "bacterium or other microorganism that induces or is capable of inducing "
            "physical distress, illness or disease.' "
            "Civil Authority extension CP 00 30: covers business income lost due to "
            "action of civil authority that prohibits access to the described premises "
            "as a direct result of damage to property other than the described premises."
        ),
        factual_disputes=(
            "Insurer position: norovirus cluster IS the 'virus' covered by CP 01 40; "
            "closure is causally related to the virus, thus excluded. Also: no 'direct "
            "physical loss' — premises were intact. "
            "Insured position: closure was the proximate cause of loss; civil-authority "
            "extension applies; norovirus exclusion was negotiated for pandemic-class "
            "epidemics, not food-safety bacterial/viral outbreaks in routine operations; "
            "regulatory closure constitutes 'damage to property other than the described "
            "premises' under the broader interpretation of damage."
        ),
        state_law=(
            "Ohio. Ohio Sup. Ct. has not directly addressed the civil-authority + "
            "virus-exclusion intersection. Federal courts applying Ohio law have split "
            "on COVID-era BI claims (Santo's Italian Cafe LLC v Acuity Ins Co, 15 F.4th "
            "398 (6th Cir 2021) — no BI for pandemic-era civil-authority closure absent "
            "physical loss). However, a single-premises foodborne-illness outbreak is "
            "distinguishable from pandemic-era population-wide closure. "
            "Contra proferentem applies under Ohio law where wording is ambiguous; "
            "reasonable-expectations doctrine recognised in commercial-policy context."
        ),
        bad_faith_exposure=(
            "Claim filed 2026-03-04. Initial reservation-of-rights NOT issued until "
            "2026-04-18 (45 days; Ohio prompt-payment statute requires substantive "
            "response within 21 days). Two prior claim-handling complaints against this "
            "insured / agent file on record (one resolved, one open). Surplus-lines "
            "policy: yes (specialty hospitality programme). Plaintiff's counsel has "
            "signalled willingness to file bad-faith counterclaim if denial is issued."
        ),
        proposed_decision=(
            "DENIAL. Basis: CP 01 40 virus exclusion applies; norovirus is a 'virus' "
            "within the plain meaning. Civil-authority extension also fails for absence "
            "of direct physical loss to other property. Reservation of rights already "
            "issued. Recommend issuing denial letter within 7 days."
        ),
    )

    workflow = CoverageDecisionWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Proposed decision: {result.metadata['proposed_decision']}")
    if result.metadata.get("vetoed"):
        print(f"\n🛑 VETO: {result.metadata['veto_reason']}")
    print()
    print(result.output)
    print()
    print("--- Coverage Counsel Checklist ---")
    for item in result.metadata["counsel_checklist"]:
        print(item)
    for label, key in [
        ("Wording Flags", "wording_flags"),
        ("Case-Law Flags", "case_law_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
