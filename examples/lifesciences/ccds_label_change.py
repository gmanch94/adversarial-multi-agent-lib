"""
CCDS Safety Label Change Review — worked example (VETO path).

Synthetic scenario: an established multi-region oral therapy (generic product
CATEGORY — no brand) with a VALIDATED serious hepatic-injury signal. The proposed
CCDS change DOWNGRADES the risk to a precaution and the rollout plan MISSES a
region's expedited safety-labeling notification window — so the reviewer is
expected to VETO (a label change that fails to convey an established serious risk
on time).

BOUNDARY (D-LIFESCI-2): distinct from PharmacovigilanceSignalWorkflow (which
detects/validates the aggregate signal). This workflow evaluates the downstream
IMPLEMENTATION of the CCDS label change across regions and the regulatory clock,
given an already-established signal. Input is the summarized signal + proposed
label text + regional divergence, not raw case narratives.

Illustrative CCDS / safety-labeling references are scenario context, not legal or
medical advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/ccds_label_change.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.ccds_label_change import (
    CCDSLabelChangeRequest,
    CCDSLabelChangeWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/ccds-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = CCDSLabelChangeRequest(
        product_description=(
            "An established oral therapy for a chronic condition, marketed across "
            "three regulatory regions."
        ),
        safety_signal_summary=(
            "A validated serious drug-induced-liver-injury signal has been "
            "established for the product (aggregate signal; case-level detail "
            "sits in the pharmacovigilance system). It meets the threshold for a "
            "safety-labeling change."
        ),
        proposed_ccds_change=(
            # DELIBERATE: downgrades the serious risk to a mere precaution.
            "Add a brief statement under the PRECAUTIONS section suggesting "
            "periodic liver-function monitoring. No Warning or Contraindication "
            "language is proposed despite the established serious signal."
        ),
        current_ccds_text=(
            "The current CCDS contains no hepatic-injury language in any section."
        ),
        regional_label_status=(
            "Regions A and B plan to adopt the precaution wording. Region C's "
            "local label update is deferred and currently omits any hepatic "
            "language."
        ),
        regulatory_timelines=(
            # DELIBERATE: the plan will miss an expedited clock.
            "Region A requires an EXPEDITED safety-labeling notification within a "
            "short mandated window of establishing the signal. Regions B and C "
            "have longer routine cycles."
        ),
        implementation_plan=(
            "Roll the change into the next two quarterly global-labeling cycles, "
            "which fall AFTER Region A's expedited notification window closes."
        ),
        benefit_risk_context=(
            "Population-level benefit-risk remains positive provided the serious "
            "hepatic risk is communicated with appropriate labeling and monitoring."
        ),
    )

    # NOTE: downgrading an established serious signal to a precaution AND missing a
    # mandatory expedited safety-labeling clock is expected to trigger a REVIEWER VETO.

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = CCDSLabelChangeWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running CCDSLabelChangeWorkflow...")
    print(f"Product: {request.product_description[:80]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()

    if result.metadata.get("vetoed"):
        print("REVIEWER VETO fired.")
        print(f"Veto reason: {result.metadata['veto_reason']}")
        print()

    print("OUTPUT:")
    print(result.output)
    print()
    print("CCDS CHECKLIST:")
    for item in result.metadata["ccds_checklist"]:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
