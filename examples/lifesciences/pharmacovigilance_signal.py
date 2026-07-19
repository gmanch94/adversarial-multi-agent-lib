"""
Pharmacovigilance Signal — worked example (veto path).

Synthetic scenario: an established oral product shows a rising disproportionality
metric for a serious hepatic event that is NOT currently in the label, and the
caller proposes to continue routine monitoring with no label change. The reviewer
is expected to issue a REVIEWER VETO — a signal meeting the threshold for
regulatory action is characterized as no-action.

Boundary (D-LIFESCI-2): distinct from the healthcare AdverseEventTriageWorkflow,
which grades a single adverse event's clinical severity/causality for a provider;
this evaluates an aggregate signal and its labeling impact for the manufacturer.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/pharmacovigilance_signal.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.pharmacovigilance_signal import (
    PharmacovigilanceSignalWorkflow,
    PVSignalRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/pharmacovigilance-signal-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = PVSignalRequest(
        product_description=(
            "An established oral small-molecule product, marketed for over a "
            "decade."
        ),
        signal_description="A rising number of serious hepatic injury reports.",
        data_source=(
            "Spontaneous safety database plus a quarterly disproportionality run."
        ),
        case_series_summary=(
            "Forty serious hepatic cases over the trailing year; several with a "
            "positive dechallenge and no clear alternative cause."
        ),
        disproportionality_metrics=(
            "EBGM elevated well above the review threshold; ROR lower bound above 1."
        ),
        causality_assessment=(
            "Caller assesses causality as unlikely, citing confounding by "
            "comorbidity."
        ),
        current_labeling="Hepatic injury is NOT currently in the product labeling.",
        proposed_action="Continue routine monitoring; no label change.",
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = PharmacovigilanceSignalWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running PharmacovigilanceSignalWorkflow...")
    print(f"Product: {request.product_description[:70]}...")
    print(f"Proposed action: {request.proposed_action}")
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
    print("PHARMACOVIGILANCE SIGNAL CHECKLIST:")
    for item in result.metadata["pv_signal_checklist"]:
        print(f"  {item}")
    print()

    ss = result.metadata["signal_strength_flags"]
    ca = result.metadata["causality_flags"]
    li = result.metadata["labeling_impact_flags"]
    if ss or ca or li:
        print(f"Signal-strength flags ({len(ss)}): {ss}")
        print(f"Causality flags ({len(ca)}): {ca}")
        print(f"Labeling-impact flags ({len(li)}): {li}")


if __name__ == "__main__":
    asyncio.run(main())
