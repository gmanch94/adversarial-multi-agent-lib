"""
Sterility Assurance Review — worked example (VETO path).

Synthetic scenario: an EO-sterilized single-use surgical device (generic device
CATEGORY — no brand). Routine bioburden trends ABOVE the validated limit and the
half-cycle validation predates a material change, while the product is proposed
for release at SAL 10^-6 — so the reviewer is expected to VETO (release of
product as sterile without a demonstrated SAL).

Illustrative ISO 11135 / ISO 11737 sterilization references are scenario context,
not legal or medical advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/sterility_assurance.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.sterility_assurance import (
    SterilityAssuranceRequest,
    SterilityAssuranceWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/sterility-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = SterilityAssuranceRequest(
        product_description=(
            "A single-use arthroscopy shaver handpiece with a polymer housing, "
            "terminally sterilized in a Tyvek/film sterile-barrier pouch."
        ),
        sterilization_method=(
            "Ethylene oxide (EO), selected for compatibility with the "
            "temperature-sensitive polymer housing and adhesives."
        ),
        sal_target="A sterility assurance level of 10^-6 is claimed.",
        bioburden_summary=(
            # DELIBERATE: bioburden trends above the validated limit.
            "Routine pre-sterilization bioburden has trended ABOVE the validated "
            "bioburden limit for three of the last four lots."
        ),
        validation_summary=(
            # DELIBERATE: validation predates a material change.
            "A half-cycle EO validation was completed 14 months ago. The polymer "
            "housing supplier and resin grade were changed 3 months ago; the cycle "
            "has not been re-validated against the new material."
        ),
        packaging_barrier=(
            "Seal-strength and dye-penetration (bubble) testing of the sterile "
            "barrier are on file and current."
        ),
        routine_control_summary=(
            "Biological indicators and residual-EO / ECH testing are run on every "
            "sterilization load; all recent loads met the BI and residual limits."
        ),
        revalidation_status=(
            "Annual EO revalidation is due; the last full revalidation was "
            "performed 13 months ago."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = SterilityAssuranceWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running SterilityAssuranceWorkflow...")
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
    print("STERILITY CHECKLIST:")
    for item in result.metadata["sterility_checklist"]:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
