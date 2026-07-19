"""
UDI Labeling — worked example (no-veto path).

Synthetic scenario: a reusable rigid endoscope whose case-level UDI is present,
but whose direct-mark DI does not match the case label DI, and one GUDID
attribute is stale relative to the current label artwork. The reviewer is
expected to flag the direct-mark mismatch (PACKAGING-TIER) and the stale GUDID
attribute (GUDID-CONSISTENCY) until the executor's review names both.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/udi_labeling.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.udi_labeling import (
    UDILabelingRequest,
    UDILabelingWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/udi-labeling-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = UDILabelingRequest(
        device_identifier=(
            "A reusable surgical instrument (rigid endoscope class), single model."
        ),
        di_pi_structure=(
            "Device Identifier plus Production Identifiers (lot and serial). DI "
            "issued as a GS1 GTIN."
        ),
        issuing_agency="GS1.",
        gudid_record_summary=(
            "GUDID record submitted with device count, sterilization method, and "
            "a brand-name attribute; the brand-name attribute predates the latest "
            "artwork revision."
        ),
        label_artwork_summary=(
            "Case label carries the human-readable UDI plus a linear barcode. The "
            "instrument body carries a direct mark."
        ),
        packaging_hierarchy="Each instrument -> single case; no inner-pack tier.",
        direct_marking_status=(
            "Direct mark present on the instrument body; the DI encoded in the "
            "mark is under review against the case label DI."
        ),
        regional_scope="United States (GUDID) and European Union (EUDAMED).",
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = UDILabelingWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running UDILabelingWorkflow...")
    print(f"Device: {request.device_identifier[:70]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()
    print("OUTPUT:")
    print(result.output)
    print()
    print("UDI LABELING CHECKLIST:")
    for item in result.metadata["udi_checklist"]:
        print(f"  {item}")
    print()

    ident = result.metadata["identifier_flags"]
    gudid = result.metadata["gudid_consistency_flags"]
    tier = result.metadata["packaging_tier_flags"]
    if ident or gudid or tier:
        print(f"Identifier flags ({len(ident)}): {ident}")
        print(f"GUDID-consistency flags ({len(gudid)}): {gudid}")
        print(f"Packaging-tier flags ({len(tier)}): {tier}")


if __name__ == "__main__":
    asyncio.run(main())
