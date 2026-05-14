"""
Environmental-impairment example — runs EnvironmentalImpairmentWorkflow on a
synthetic former-dry-cleaner site (PCE/TCE groundwater plume, Pennsylvania,
state Superfund + EPA RCRA + Brownfields overlay).

Veto + triple-flag (KNOWN-CONDITION / TAIL / REGULATORY-OVERLAP).

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.pc.environmental_impairment
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.pc.workflows.environmental_impairment import (
    EnvironmentalImpairmentRequest,
    EnvironmentalImpairmentWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = EnvironmentalImpairmentRequest(
        site_summary=(
            "Former dry-cleaner / current office park (mixed-use). Allegheny County, PA. "
            "Building constructed 1962; dry-cleaner operation 1968–2001; redeveloped as "
            "office in 2004 by current named insured (Reeves Capital Partners LLC). "
            "Acquired by current owner 2022 with Phase I ESA at acquisition."
        ),
        site_history=(
            "1968–2001: 33 years of perchloroethylene (PCE) dry-cleaning operation. "
            "1988: leaking USTs removed; soil contamination documented. "
            "1996: state DEP NOV for floor-drain discharge to subsurface (settled with "
            "consent order, voluntary cleanup partial). "
            "2001: dry-cleaner ceased operations; partial site assessment performed. "
            "2004: redevelopment without full remediation. "
            "Phase I ESA (2022): identified 1996 consent order as REC; recommended "
            "Phase II. Phase II (2023): PCE 1,200 ug/L groundwater @ MW-3 (exceeds MCL "
            "5 ug/L by 240x); TCE detected (PCE degradation product). Plume direction: "
            "westward toward adjacent commercial parcel."
        ),
        pollution_condition=(
            "Discovered: 2024-09 — claim notice. Allegation: PCE-contaminated "
            "groundwater migrated under adjacent parcel (Sterling Logistics warehouse); "
            "Sterling discovered indoor-air PCE vapors during HVAC replacement 2024-08. "
            "Sterling has filed third-party PD + BI claim against insured; alleges "
            "stigma damages + remediation + worker indoor-air exposure."
        ),
        policy_form=(
            "Pollution Legal Liability (PLL) form, 3-year claims-made + reported, "
            "$5M aggregate / $2M each-claim. Retroactive date: 2022-08-15 (acquisition "
            "date). Key clauses: Insuring Agreement A (on-site remediation), "
            "Insuring Agreement B (third-party BI/PD), Known-Condition Exclusion "
            "(I.1.f: any condition known to insured or disclosed to underwriter prior "
            "to retroactive date). Claim-series clause links related claims. "
            "Sub-limit for NRD: $1M."
        ),
        governing_state=(
            "Pennsylvania. PA Sup. Ct. recognises continuous-trigger doctrine for "
            "long-tail environmental claims (J.H. France Refractories Co v Allstate "
            "Ins Co, 626 A.2d 502 (Pa. 1993)). PA also follows Koppers Co allocation "
            "(pro-rata by years on risk). Statute of repose for environmental claims: "
            "20 years (42 Pa. C.S. § 5524.1)."
        ),
        regulator_status=(
            "PA DEP: NOT NPL-listed (federal); IS listed on PA Hazardous Site Cleanup "
            "Act (HSCA) inventory due to 1996 consent order. EPA RCRA: NOT a generator "
            "of record post-2001. CERCLA: no federal PRP determination. Brownfields "
            "agreement: NOT entered (would have required full Act 2 review). "
            "Natural Resource Damages: surface-water adjacent (Saw Mill Run); PA "
            "Game Commission and Fish & Boat Commission are NRD trustees."
        ),
        co_insurer_history=(
            "Insured carried prior environmental coverage 2004–2021 via 3 different "
            "carriers (records on file). 1968–2001 dry-cleaner operator carried "
            "general-liability coverage; identity of those carriers unknown without "
            "policy archaeology (former dry-cleaner is dissolved entity). PRE-2022 "
            "carriers all face continuous-trigger allocation under PA law."
        ),
        proposed_decision_or_reserve=(
            "Proposed: DENY coverage under known-condition exclusion (I.1.f). Basis: "
            "Phase I ESA identified 1996 consent order as REC; current insured had "
            "actual knowledge of the consent order at acquisition (2022); the PCE "
            "groundwater contamination is a continuation of the very condition that "
            "the 1996 consent order addressed. Reservation of rights already issued. "
            "Reserve recommendation if coverage attaches: $4.2M (within $5M aggregate; "
            "includes Phase II / FS / RD-RA mid-band + $1M NRD sub-limit + 35% defence)."
        ),
    )

    workflow = EnvironmentalImpairmentWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Site: {result.metadata['site_summary'][:80]}...")
    if result.metadata.get("vetoed"):
        print(f"\n🛑 VETO: {result.metadata['veto_reason']}")
    print()
    print(result.output)
    print()
    print("--- Environmental Counsel Checklist ---")
    for item in result.metadata["counsel_checklist"]:
        print(item)
    for label, key in [
        ("Known-Condition Flags", "known_condition_flags"),
        ("Tail Flags", "tail_flags"),
        ("Regulatory-Overlap Flags", "regulatory_overlap_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
