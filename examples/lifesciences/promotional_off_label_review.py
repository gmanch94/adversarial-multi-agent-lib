"""
Promotional Off-Label / Fair-Balance Review — worked example (veto path).

Synthetic scenario (generic category, no brand): a healthcare-professional
visual aid for an established oral small-molecule therapy makes a claim promoting
use in a pediatric population that falls outside the approved adult indication,
while the important safety information (including a boxed warning) is relegated to
under-prominent fine print. Releasing the material would likely draw an FDA
enforcement or untitled letter.

The reviewer is expected to issue a REVIEWER VETO — the material would likely draw
an FDA enforcement/untitled letter (off-label promotion plus omission of material
risk); escalate to the MLR committee and do not release the material.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/promotional_off_label_review.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.promotional_off_label_review import (
    PromotionalOffLabelReviewWorkflow,
    PromoReviewRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/promo-review-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    # An HCP visual aid for an established oral therapy promoting an off-label
    # pediatric population while the boxed warning is under-prominent — clear
    # off-label promotion plus omission of material risk → reviewer VETO path.
    request = PromoReviewRequest(
        material_type=(
            "A healthcare-professional visual aid (leave-behind detail piece) for "
            "an established oral small-molecule therapy."
        ),
        target_audience=(
            "Prescribing physicians (specialist HCP audience)."
        ),
        promo_claims=(
            "Claim 1: reduces symptom burden within the approved adult indication. "
            "Claim 2: 'now an option for pediatric patients as young as 6' — "
            "promotes use in children. Claim 3: better tolerated than the standard "
            "of care."
        ),
        approved_labeling_reference=(
            "Approved labeling: indicated for ADULTS only with the on-label "
            "condition; a boxed warning for a known serious adverse reaction; "
            "pediatric use has NOT been established and is not in the label."
        ),
        cited_references=(
            "One pivotal adult randomised controlled trial. No pediatric trial is "
            "cited. The tolerability comparison cites a non-head-to-head post-hoc "
            "pooling."
        ),
        risk_information_present=(
            "Important safety information, including the boxed warning, appears "
            "only in small footnote text on the back panel — far less prominent "
            "than the benefit claims on the front."
        ),
        comparative_claims=(
            "'Better tolerated than the standard of care' — a comparative claim "
            "supported only by a non-head-to-head post-hoc analysis."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = PromotionalOffLabelReviewWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running PromotionalOffLabelReviewWorkflow...")
    print(f"Material type: {request.material_type[:80]}...")
    print(f"Target audience: {request.target_audience[:80]}...")
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
    print("PROMO CHECKLIST:")
    for item in result.metadata["promo_checklist"]:
        print(f"  {item}")
    print()

    off = result.metadata["off_label_flags"]
    fair = result.metadata["fair_balance_flags"]
    sub = result.metadata["substantiation_flags"]
    if off or fair or sub:
        print(f"Off-label flags ({len(off)}): {off}")
        print(f"Fair-balance flags ({len(fair)}): {fair}")
        print(f"Substantiation flags ({len(sub)}): {sub}")


if __name__ == "__main__":
    asyncio.run(main())
