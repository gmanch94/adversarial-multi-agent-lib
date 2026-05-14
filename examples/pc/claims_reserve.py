"""
Claims-reserve example — runs ClaimsReserveWorkflow with a synthetic
commercial bodily-injury scenario (premises-liability slip-and-fall with
TBI severity tier).

This demonstrates the reviewer-veto pattern (D-PC-4): the reviewer can
halt the workflow regardless of score if reserve adequacy poses
SOX-restatement risk.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.pc.claims_reserve
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.pc.workflows.claims_reserve import (
    ClaimsReserveRequest,
    ClaimsReserveWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = ClaimsReserveRequest(
        loss_event=(
            "2026-04-18 14:25 ET — claimant Jane R. (age 47, retail associate at "
            "third-party vendor) slipped on standing water near self-checkout 4 at "
            "named insured's grocery store, Hamilton County OH. Insured: GreenLeaf "
            "Markets LLC, GL policy GL-PREM-2026-44871, occurrence-based."
        ),
        injury_or_damage=(
            "Tier: SEVERE. Claimant struck back of head on concrete floor; transported "
            "to Cincinnati General. Diagnoses: closed traumatic brain injury (Glasgow 11 "
            "at admission), subdural hematoma, post-concussive syndrome with persistent "
            "cognitive deficit at 6-week eval. Treating neurologist: 'unlikely to return "
            "to pre-injury cognitive baseline; partial permanent disability likely.' "
            "Pre-injury earnings: ~$42k/yr; remaining work-life expectancy ~18 years."
        ),
        coverage_summary=(
            "GL form CG 00 01 04 13. Per-occurrence limit: $1,000,000. General aggregate: "
            "$2,000,000. SIR: $25,000 (insured already exhausted). Bodily injury and "
            "property damage liability coverage A; no umbrella attached at this layer. "
            "No relevant exclusions endorsed; standard premises-condition coverage."
        ),
        comparable_cases=(
            "Hamilton County OH 2024: $725k settlement (premises slip TBI, similar age, "
            "Glasgow 13). Hamilton County OH 2023: $1.1M verdict (premises slip TBI, "
            "younger claimant, more severe cognitive deficit). Franklin County OH 2024: "
            "$540k settlement (peer county, similar facts). Cuyahoga County OH 2022: "
            "$1.4M verdict (more plaintiff-friendly county, more severe injury). "
            "Median of Hamilton + Franklin (venue-matched) ≈ $725k."
        ),
        venue=(
            "Hamilton County, Ohio, Court of Common Pleas. Jury verdicts: classified "
            "moderate-plaintiff-friendly per Jury Verdict Reporter regional table; "
            "median premises-TBI verdict 2020-2025 ≈ $810k."
        ),
        defense_posture=(
            "Liability: standing water from leaking refrigeration unit known to staff "
            "30 minutes prior to incident per surveillance review; no wet-floor sign "
            "deployed. Comparative fault assessment: claimant 10% (wearing low-traction "
            "footwear, on phone at moment of fall). Ohio is modified comparative-fault "
            "(51% bar). Liability likely admitted; quantum is the dispute."
        ),
        medical_or_repair_estimate=(
            "Medical specials to date: $86k. Projected future medical (cognitive rehab, "
            "neuropsych monitoring, attendant care 8 hrs/wk): treating-provider estimate "
            "$240k over remaining lifetime. Lost wages to date: $14k; future lost-earning-"
            "capacity (with 30% impairment): ~$190k present value. Non-economic exposure: "
            "Ohio non-economic cap for non-catastrophic ≈ $250k; for catastrophic injury "
            "(TBI with permanent disability) cap may not apply."
        ),
        regulatory_exposure=(
            "No state AG inquiry. No DOI exam. Plaintiff's counsel has signalled "
            "intention to seek catastrophic-injury exception to non-economic cap, which "
            "would change the upper-bound exposure materially. Single claimant; no "
            "class-action or multi-claimant pattern."
        ),
        current_reserve_proposal=(
            "Analyst first-pass: $620,000 indemnity (below venue median, citing 10% "
            "comparative-fault reduction). Defence cost: $95,000 (15% of indemnity, "
            "routine-tier assumption). IBNR uplift: not stated. Total: $715,000."
        ),
    )

    workflow = ClaimsReserveWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Loss event: {result.metadata['loss_event']}")
    if result.metadata.get("vetoed"):
        print(f"\n🛑 VETO: {result.metadata['veto_reason']}")
    print()
    print(result.output)
    print()
    print("--- Actuary / Claims Committee Checklist ---")
    for item in result.metadata["actuary_checklist"]:
        print(item)
    for label, key in [
        ("Reserve Flags", "reserve_flags"),
        ("Precedent Flags", "precedent_flags"),
        ("Litigation Flags", "litigation_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
