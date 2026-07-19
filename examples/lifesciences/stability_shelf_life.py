"""
Stability / Shelf-Life — worked example (no-veto path).

Synthetic scenario: an oral solid-dose immediate-release tablet proposing a
36-month shelf life from 12 months of long-term data plus 6 months accelerated,
with a slight downward assay drift. The reviewer is expected to flag the
over-extrapolation (EXTRAPOLATION) and the assay trend (TREND) until the
executor's review addresses both against the data under ICH Q1E.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/stability_shelf_life.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.stability_shelf_life import (
    StabilityShelfLifeRequest,
    StabilityShelfLifeWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/stability-shelf-life-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = StabilityShelfLifeRequest(
        product_description=(
            "Oral solid-dose immediate-release tablet packaged in HDPE bottles "
            "with desiccant."
        ),
        proposed_shelf_life="36 months at 25C/60%RH.",
        storage_conditions="Long-term 25C/60%RH; accelerated 40C/75%RH.",
        stability_data_summary=(
            "3 primary batches; long-term timepoints 0/3/6/9/12 months; "
            "accelerated 0/3/6 months; attributes assay, dissolution, impurities."
        ),
        specification_limits=(
            "Assay 95.0-105.0%; total impurities <= 1.0%; dissolution Q >= 80% "
            "at 30 minutes."
        ),
        trend_analysis_summary=(
            "Assay shows a slight downward drift across 12 months (100.5% -> "
            "98.7%); impurities stable; dissolution stable."
        ),
        oos_oot_events=(
            "No OOS results. One borderline dissolution OOT at 9 months was "
            "investigated and closed as method variability."
        ),
        extrapolation_basis=(
            "Caller proposes 36 months from 12 months long-term data plus 6 "
            "months accelerated data, citing ICH Q1E."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = StabilityShelfLifeWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running StabilityShelfLifeWorkflow...")
    print(f"Product: {request.product_description[:70]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()
    print("OUTPUT:")
    print(result.output)
    print()
    print("STABILITY CHECKLIST:")
    for item in result.metadata["stability_checklist"]:
        print(f"  {item}")
    print()

    ex = result.metadata["extrapolation_flags"]
    tr = result.metadata["trend_flags"]
    sp = result.metadata["spec_exceedance_flags"]
    if ex or tr or sp:
        print(f"Extrapolation flags ({len(ex)}): {ex}")
        print(f"Trend flags ({len(tr)}): {tr}")
        print(f"Spec-exceedance flags ({len(sp)}): {sp}")


if __name__ == "__main__":
    asyncio.run(main())
