"""
Gig-platform-liability example — runs GigPlatformLiabilityWorkflow on a
synthetic multi-state on-demand-skilled-trades platform (3-state operation:
CA / TX / FL; mix of 1099 contractors; pending CA AB5 class-action signal).

Veto + triple-flag (CLASSIFICATION / COVERAGE-GAP / REGULATORY-PATCHWORK).

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.pc.gig_platform_liability
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.pc.workflows.gig_platform_liability import (
    GigPlatformLiabilityRequest,
    GigPlatformLiabilityWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = GigPlatformLiabilityRequest(
        platform_summary=(
            "FixIt Now Inc. — on-demand skilled-trades platform connecting consumers "
            "with HVAC technicians, electricians, plumbers, and appliance repair pros. "
            "States of operation: California, Texas, Florida. Worker count: 4,800 "
            "active 1099 contractors (CA: 1,950; TX: 1,720; FL: 1,130). Annual "
            "platform GMV: $148M; platform revenue (15% take rate): $22.2M. "
            "Service type: same-day skilled-trades dispatch."
        ),
        workforce_classification=(
            "All 4,800 contractors classified 1099 by FixIt. CA: NOT carved out under "
            "Prop 22 (Prop 22 covers app-based drivers / delivery only, NOT skilled "
            "trades). Platform claims AB5 ABC-test prong B is satisfied (trades work "
            "outside FixIt's 'usual course' of being a marketplace). Pending class "
            "action filed 2026-02 in Alameda County: Garcia v FixIt Now (alleges AB5 "
            "misclassification across CA workforce; 1,950 putative class members). "
            "TX / FL: platform claims common-law contractor status; no state-statutory "
            "challenge yet."
        ),
        coverage_stack=(
            "Commercial GL: $5M / $10M aggregate (covers platform entity). "
            "Excess liability: $25M tower. "
            "Occupational accident: $500k AD&D + medical-expense-only, no wage-replacement "
            "(used as WC substitute in TX / FL; NOT recognised as WC substitute in CA "
            "for skilled trades). "
            "Contingent commercial auto: $1M/$1M (over worker's personal auto, while "
            "engaged en route to job). "
            "EPLI: $3M (covers platform employer-liability exposure to W-2 "
            "headcount only; NO coverage for 1099 contractor misclassification "
            "retroactive WC). "
            "NO retroactive-reclassification rider."
        ),
        personal_policy_context=(
            "FixIt requires workers to carry: (a) personal auto with commercial-use "
            "endorsement OR commercial auto $300k/$300k; (b) personal GL or trade-"
            "specific GL. Compliance audit shows only ~62% of CA workers have valid "
            "commercial-auto endorsement; ~40% of TX/FL workers have any commercial "
            "policy. Platform-on / Platform-off definition: 'engaged in active job "
            "with FixIt customer per timestamp in worker app.' En-route-to-job period: "
            "ambiguous — platform's contingent auto covers 'en-route' but the policy "
            "defines en-route as 'after acceptance of job, prior to arrival'; worker "
            "app does not timestamp 'acceptance' separately from 'job start.'"
        ),
        state_regulatory_posture=(
            "CALIFORNIA: AB5 ABC-test applies (no Prop 22 for skilled trades). State "
            "AG sent inquiry letter to FixIt 2026-01 re: classification. Pending "
            "Garcia class action. CA EDD has been auditing similar platforms. "
            "TEXAS: common-law test; TX Workforce Commission has no posted position "
            "on skilled-trades platforms; TX Insurance Code 1954 does NOT cover "
            "skilled-trades (TNC statute is rideshare-specific). "
            "FLORIDA: § 627.748 TNC statute does NOT cover skilled-trades. FL DEO "
            "audited a similar platform 2025 and assessed UI back-tax."
        ),
        pending_litigation=(
            "Garcia v FixIt Now (Alameda Sup. Ct., filed 2026-02) — putative class of "
            "1,950 CA contractors alleging AB5 misclassification, unpaid OT, expense "
            "reimbursement under CA Labor Code § 2802. Plaintiff signalled PAGA notice "
            "filed concurrently. CA AG inquiry letter 2026-01 cited as related. "
            "FL DEO assessment against peer platform 2025 noted as risk signal. "
            "NLRB: no current charge; broader skilled-trades-platform NLRB activity "
            "trending toward joint-employer findings."
        ),
        proposed_bind_or_decision=(
            "Proposed renewal terms: GL premium $385k (8% rate increase YoY); "
            "EPLI $124k (15% increase reflecting Garcia exposure); occ-acc reduced "
            "from $500k to $300k in CA (in recognition of CA non-substitution); "
            "ADD condition precedent: FixIt must achieve >85% worker personal-auto "
            "compliance in CA by renewal effective date. "
            "NO retroactive-reclassification rider proposed. "
            "NO bridge endorsement for the en-route-to-job timestamp ambiguity."
        ),
    )

    workflow = GigPlatformLiabilityWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Platform: {result.metadata['platform_summary'][:80]}...")
    if result.metadata.get("vetoed"):
        print(f"\n🛑 VETO: {result.metadata['veto_reason']}")
    print()
    print(result.output)
    print()
    print("--- Platform-Liability Counsel Checklist ---")
    for item in result.metadata["counsel_checklist"]:
        print(item)
    for label, key in [
        ("Classification Flags", "classification_flags"),
        ("Coverage-Gap Flags", "coverage_gap_flags"),
        ("Regulatory-Patchwork Flags", "regulatory_patchwork_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
