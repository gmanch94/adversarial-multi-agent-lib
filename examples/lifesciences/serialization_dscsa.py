"""
Serialization / DSCSA Traceability Review — worked example (no-veto path).

Synthetic scenario: an oral solid-dose prescription product (generic product
CATEGORY — no brand) in a bottle/case/pallet hierarchy. The configuration has a
DELIBERATE aggregation gap — item-to-case links are missing for a repackaged lot —
and saleable returns are verified only at the lot level, not the unit serial, so
the reviewer is expected to raise AGGREGATION (and likely SALEABLE-RETURN) flags
and the workflow should NOT converge on the first round.

Illustrative DSCSA / GS1 EPCIS references are scenario context, not legal or
regulatory advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/serialization_dscsa.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.serialization_dscsa import (
    SerializationDSCSARequest,
    SerializationDSCSAWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/serialization-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = SerializationDSCSARequest(
        product_description=(
            "An oral solid-dose prescription product packaged in unit bottles, "
            "shipper cases, and pallets."
        ),
        serialization_scheme=(
            "Each saleable unit (bottle) carries a 2D DataMatrix encoding GTIN, "
            "unit serial number, lot number, and expiration date."
        ),
        aggregation_summary=(
            # DELIBERATE: item-to-case aggregation missing for a repackaged lot.
            "Case-to-pallet aggregation is captured on the palletizer. For one "
            "lot that was repackaged after a line stoppage, the item-to-case "
            "(bottle-to-case) aggregation links were NOT re-captured."
        ),
        epcis_events=(
            "Commissioning, packing, and shipping EPCIS events are captured at "
            "the packaging line and warehouse."
        ),
        trading_partner_exchange=(
            "EPCIS documents are exchanged with authorized trading partners at "
            "each change of ownership."
        ),
        verification_process=(
            "Product-identifier verification is available for suspect product "
            "through the verification router."
        ),
        saleable_returns_process=(
            # DELIBERATE: returns verified at lot level, not unit level.
            "Saleable returns are checked against the lot number and expiry "
            "before being returned to saleable stock; the individual unit serial "
            "is not verified against the traceability data."
        ),
        interoperability_status=(
            "The system exchanges EPCIS today and is being upgraded toward "
            "enhanced unit-level (interoperable) traceability."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = SerializationDSCSAWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running SerializationDSCSAWorkflow...")
    print(f"Product: {request.product_description[:80]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()

    print("OUTPUT:")
    print(result.output)
    print()
    print("SERIALIZATION CHECKLIST:")
    for item in result.metadata["serialization_checklist"]:
        print(f"  {item}")
    print()

    ag = result.metadata["aggregation_flags"]
    tr = result.metadata["traceability_flags"]
    sr = result.metadata["saleable_return_flags"]
    if ag or tr or sr:
        print(f"Aggregation flags ({len(ag)}): {ag}")
        print(f"Traceability flags ({len(tr)}): {tr}")
        print(f"Saleable-return flags ({len(sr)}): {sr}")


if __name__ == "__main__":
    asyncio.run(main())
