"""
CGT Durability / Curative Claim Substantiation Review — worked example (veto path).

Synthetic scenario (generic category, no brand): a one-time AAV gene therapy
proposes a curative labeling claim resting on a 6-month biomarker with no
durability data. The claim overstates benefit and creates misbranding and
patient-harm exposure.

The reviewer is expected to issue a REVIEWER VETO — remove the curative claim and
limit to the observed follow-up window.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/cgt_durability_claim.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.cgt_durability_claim import (
    CGTDurabilityClaimWorkflow,
    DurabilityClaimRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/cgt-durability-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = DurabilityClaimRequest(
        product_description="A one-time AAV gene therapy for a monogenic disorder.",
        proposed_claim=(
            "A single administration provides a curative, lifelong correction of the "
            "underlying disorder."
        ),
        pivotal_efficacy_summary=(
            "The pivotal study met a 6-month biomarker endpoint; no longer-term "
            "clinical outcome was measured."
        ),
        followup_duration_and_n=(
            "24 patients dosed; median follow-up 6 months; substantial censoring "
            "beyond 6 months."
        ),
        durability_evidence=(
            "No data beyond 6 months; expression durability and loss-of-response are "
            "unknown."
        ),
        population_and_endpoint=(
            "Adults with the disorder; endpoint is a 6-month biomarker, not a "
            "clinical outcome."
        ),
        comparator_or_natural_history=(
            "Natural history is variable; no comparator arm in the pivotal study."
        ),
        label_context=(
            "The curative claim is proposed for the headline of promotional and "
            "labeling materials."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = CGTDurabilityClaimWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running CGTDurabilityClaimWorkflow...")
    print(f"Product: {request.product_description[:80]}...")
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
    print("DURABILITY CHECKLIST:")
    for item in result.metadata["durability_checklist"]:
        print(f"  {item}")
    print()

    dur = result.metadata["durability_claim_flags"]
    fu = result.metadata["followup_evidence_flags"]
    cur = result.metadata["curative_language_flags"]
    if dur or fu or cur:
        print(f"Durability-claim flags ({len(dur)}): {dur}")
        print(f"Followup-evidence flags ({len(fu)}): {fu}")
        print(f"Curative-language flags ({len(cur)}): {cur}")


if __name__ == "__main__":
    asyncio.run(main())
