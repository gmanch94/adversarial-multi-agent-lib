"""
Bioequivalence Assessment — worked example (VETO path).

Synthetic scenario: a generic modified-release oral tablet (generic product
CATEGORY — no brand). The Cmax 90% confidence interval upper bound reaches 128%
under fed conditions (OUTSIDE the 80.00-125.00% limits), yet the caller concludes
bioequivalence on the AUC result alone — so the reviewer is expected to VETO (a
bioequivalence conclusion the data do not support).

Illustrative bioequivalence / ICH M13 references are scenario context, not legal
or medical advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/bioequivalence.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.bioequivalence import (
    BioequivalenceRequest,
    BioequivalenceWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/bioequivalence-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = BioequivalenceRequest(
        product_description=(
            "A generic modified-release oral tablet compared against the "
            "reference listed drug for an ANDA submission."
        ),
        study_design=(
            "A two-way, two-period, two-sequence single-dose crossover conducted "
            "under both fasting and fed conditions."
        ),
        pk_parameters=(
            # DELIBERATE: Cmax CI is out of range under fed conditions.
            "Fasting: AUC0-t and Cmax 90% CIs both within 80.00-125.00%. Fed: "
            "AUC0-t 90% CI within limits; Cmax 90% CI is 108% to 128%, so the "
            "upper bound (128%) is ABOVE the 125% limit."
        ),
        study_population=(
            "36 healthy adult volunteers completed both periods."
        ),
        statistical_analysis=(
            "ANOVA on log-transformed AUC and Cmax; moderate intra-subject "
            "variability; a standard (non-replicate) crossover design."
        ),
        boundary_results=(
            "The fed-condition Cmax 90% CI upper bound crosses the 125% "
            "bioequivalence limit; all other parameters are within limits."
        ),
        biowaiver_basis=(
            "No BCS-based biowaiver is claimed for this modified-release product."
        ),
        special_considerations=(
            "The drug is not narrow-therapeutic-index and is not classified as "
            "highly variable, so the standard 80.00-125.00% limits apply and "
            "cannot be widened."
        ),
    )

    # NOTE: concluding bioequivalence on the AUC result while the fed Cmax 90% CI
    # sits outside the limits (with no basis to widen them) is expected to trigger
    # a REVIEWER VETO.

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = BioequivalenceWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running BioequivalenceWorkflow...")
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
    print("BIOEQUIVALENCE CHECKLIST:")
    for item in result.metadata["bioequivalence_checklist"]:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
