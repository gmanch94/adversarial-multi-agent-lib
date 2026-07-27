"""
CGT Post-Change Comparability Review — worked example (veto path).

Synthetic scenario (generic category, no brand): an autologous gene-modified cell
therapy changes its lentiviral vector supplier and scales up transduction, then
argues comparability on a limited analytical panel with no clinical bridge. The
new vector alters the integration profile and shifts the potency distribution —
making it a materially different product that cannot be treated as comparable
without new clinical data.

The reviewer is expected to issue a REVIEWER VETO — generate bridging clinical
data before implementing the change.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/cgt_comparability.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os
import tempfile

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.cgt_comparability import (
    CGTComparabilityWorkflow,
    ComparabilityRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir=tempfile.mkdtemp(prefix="cgt-comparability-example-"),
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = ComparabilityRequest(
        product_description="An autologous gene-modified cell therapy.",
        change_description=(
            "A change of the lentiviral vector supplier and a two-fold scale-up of "
            "the transduction step."
        ),
        pre_change_process_summary=(
            "Vector from supplier A; transduction at the original scale; a "
            "characterised integration profile and potency distribution."
        ),
        post_change_process_summary=(
            "Vector from supplier B; transduction at two-fold scale; the integration "
            "profile shifts and the potency distribution moves relative to the "
            "pre-change product."
        ),
        analytical_comparability_data=(
            "Identity, purity, and VCN compared on two post-change lots; integration "
            "profile and potency distribution were NOT compared side-by-side."
        ),
        quality_attribute_panel="Identity, purity, potency, VCN, sterility, viability.",
        clinical_bridging_plan=(
            "No clinical bridge proposed; comparability asserted on the limited "
            "analytical panel."
        ),
        risk_assessment_summary=(
            "Risk described as low, understating the vector-change impact on "
            "integration and potency."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")
    print(f"Workspace (per-run, isolated): {config.workspace_dir}")

    workflow = CGTComparabilityWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running CGTComparabilityWorkflow...")
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
    print("COMPARABILITY CHECKLIST:")
    for item in result.metadata["comparability_checklist"]:
        print(f"  {item}")
    print()

    pd = result.metadata["process_delta_flags"]
    ag = result.metadata["analytical_gap_flags"]
    cb = result.metadata["clinical_bridge_flags"]
    if pd or ag or cb:
        print(f"Process-delta flags ({len(pd)}): {pd}")
        print(f"Analytical-gap flags ({len(ag)}): {ag}")
        print(f"Clinical-bridge flags ({len(cb)}): {cb}")


if __name__ == "__main__":
    asyncio.run(main())
