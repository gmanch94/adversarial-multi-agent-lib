"""
Parametric-crop example — runs ParametricCropWorkflow on a synthetic rainfall-
index cover for a Kansas dryland-wheat producer (heat-shifted climate region,
drought-dominant loss history, NOAA-station data source).

Triple-flag (PERIL-MATCH / BASIS / ATTACHMENT); no veto.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.pc.parametric_crop
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.pc.workflows.parametric_crop import (
    ParametricCropRequest,
    ParametricCropWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = ParametricCropRequest(
        producer_summary=(
            "Heartland Grain Cooperative member: Lindgren Farms, Stafford County KS. "
            "Dryland (non-irrigated) operation; 2,400 acres planted to hard red winter "
            "wheat; conventional rotation (wheat-fallow on most acres). Producer family "
            "since 1958; current operator generation since 2018."
        ),
        crop_and_yield_history=(
            "Hard red winter wheat. APH 10-yr (2015-2024): 38 bu/ac (county T-yield "
            "32 bu/ac). Year-by-year: 42, 45, 28, 41, 12, 44, 39, 21, 47, 41. "
            "2017 and 2022 catastrophic-yield years aligned with severe spring drought + "
            "heat stress during heading/grain-fill. 2024 was a recovery year."
        ),
        loss_history=(
            "5-year cause-by-cause: 2020 drought / heat ($412k indemnified under MPCI), "
            "2022 drought / heat ($380k indemnified under MPCI), 2023 minor hail "
            "($28k under crop-hail rider). No freeze losses in 5-yr window. No moisture-"
            "excess losses. Producer is shopping a parametric add-on to layer ABOVE "
            "MPCI deductible (basis-risk catastrophe layer)."
        ),
        proposed_cover_type=(
            "Rainfall-Index parametric add-on. Trigger: cumulative rainfall at NOAA "
            "station Stafford-1 (Apr-Jun, critical-growth window) below 6.0 inches "
            "(20-yr 30th-percentile). Payout: linear $50/ac up to $150/ac at 3.5 in "
            "(historic 10th-percentile). Coverage: 2,400 acres × $150/ac = $360k max "
            "per growing season. Cover term: April 1 – June 30 each year, multi-year."
        ),
        data_source=(
            "NOAA Cooperative Observer station 'Stafford 1' (USC00147747). Station "
            "uptime 1948–present, 96% data-completeness in last 20 yrs. Station "
            "location: 16 miles NE of the centroid of the producer's wheat acreage. "
            "Producer's wheat is spread across 14 separately-titled tracts; max tract "
            "distance from station: 27 miles."
        ),
        climate_baseline=(
            "20-yr Apr-Jun rainfall at Stafford-1: mean 8.4 in, std-dev 2.7 in. "
            "Trend (2005–2024 linear): -0.18 in/decade (drying). Last 5 yrs: 6.8 in "
            "mean (markedly below 20-yr). Implied as-is loss-cost at 6.0 in trigger: "
            "~14% per year. De-trended loss-cost: ~9%. Climate-creep magnitude: "
            "+5 percentage points (i.e. trigger is moving from 30th-percentile toward "
            "median over the back-test window)."
        ),
        reinsurance_context=(
            "MPCI base layer is RMA-reinsured under SRA Group 1 (Kansas commercial "
            "fund). The parametric add-on is OUTSIDE the SRA: commercial retro layered "
            "by Bermudan reinsurer at 50% quota share with $5M cat aggregate per crop-"
            "season. Aggregate headroom currently $2.1M. This bind would consume $360k "
            "of available aggregate."
        ),
    )

    workflow = ParametricCropWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Producer: {result.metadata['producer_summary'][:80]}...")
    print(f"Cover type: {result.metadata['proposed_cover_type'][:80]}...")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for label, key in [
        ("Peril-Match Flags", "peril_match_flags"),
        ("Basis Flags", "basis_flags"),
        ("Attachment Flags", "attachment_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
