"""
Cold-Chain Excursion Disposition — worked example (VETO path).

Synthetic scenario: a refrigerated biologic (generic product CATEGORY — no brand)
labeled 2-8 degrees Celsius. Two above-range legs sum to a cumulative excursion
that EXCEEDS the documented stability budget, yet the caller proposes release
citing "brief" legs — so the reviewer is expected to VETO (release of product
whose cumulative excursion exceeds its stability budget).

Illustrative stability / mean-kinetic-temperature references are scenario context,
not legal or medical advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/cold_chain_excursion.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.cold_chain_excursion import (
    ColdChainExcursionRequest,
    ColdChainExcursionWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/coldchain-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = ColdChainExcursionRequest(
        product_description=(
            "A refrigerated biologic (lyophilized-then-reconstituted therapeutic "
            "protein) labeled for storage at 2-8 degrees Celsius."
        ),
        excursion_description=(
            "The shipment was held on an uncooled loading dock during a carrier "
            "delay, then again at a distribution hub, on two separate legs of "
            "transit, at temperatures above 8 degrees Celsius (peaking near 22 C)."
        ),
        label_storage_condition="Store at 2-8 degrees Celsius. Do not freeze.",
        stability_budget_summary=(
            "Supporting stability data establish a TOTAL allowable excursion budget "
            "of 24 hours cumulative above 8 degrees Celsius over the product's "
            "shelf life before potency is at risk."
        ),
        excursion_extent=(
            # DELIBERATE: cumulative exceeds the budget, and the caller did not sum.
            "Leg one: approximately 14 hours above range. Leg two: approximately "
            "16 hours above range. The caller assessed each leg separately and did "
            "NOT sum them (cumulative is approximately 30 hours)."
        ),
        affected_units=(
            "Two shipper pallets from a single manufacturing lot in the affected "
            "shipment."
        ),
        impact_on_quality=(
            # DELIBERATE: understates impact by treating legs independently.
            "The caller states the product is unaffected because 'each individual "
            "excursion leg was brief and within tolerance'."
        ),
        proposed_disposition="Release to distribution.",
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = ColdChainExcursionWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running ColdChainExcursionWorkflow...")
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
    print("COLD-CHAIN CHECKLIST:")
    for item in result.metadata["coldchain_checklist"]:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
