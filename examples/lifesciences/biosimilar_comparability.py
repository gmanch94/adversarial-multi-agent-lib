"""
Biosimilar Comparability Assessment — worked example (VETO path).

Synthetic scenario: a proposed biosimilar monoclonal antibody (generic product
CATEGORY — no brand). A glycosylation critical quality attribute falls OUTSIDE the
reference range while the caller concludes biosimilarity and extrapolates to all
indications — so the reviewer is expected to VETO (a biosimilarity conclusion the
comparability data do not support).

Illustrative FDA 351(k) / ICH comparability references are scenario context, not
legal or medical advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/biosimilar_comparability.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.biosimilar_comparability import (
    BiosimilarComparabilityRequest,
    BiosimilarComparabilityWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/biosimilar-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = BiosimilarComparabilityRequest(
        product_description=(
            "A proposed biosimilar monoclonal antibody referencing an approved "
            "oncology reference product. Sought as biosimilar across all reference "
            "indications."
        ),
        analytical_similarity_summary=(
            "Primary amino-acid sequence identical to the reference. Higher-order "
            "structure comparable by orthogonal methods. Glycosylation profile "
            "assessed by released-glycan mapping."
        ),
        quality_attributes=(
            "Critical quality attributes and risk tier: glycosylation (afucosylation "
            "level) HIGH — linked to ADCC potency; charge variants MEDIUM; "
            "aggregation MEDIUM; potency HIGH."
        ),
        pk_pd_summary=(
            "A single-dose PK crossover in healthy volunteers met the 80.00-125.00 "
            "percent equivalence margins for the primary PK parameters."
        ),
        clinical_comparability_summary=(
            "A comparative efficacy and immunogenicity study in one sensitive "
            "indication showed no clinically meaningful difference in response rate "
            "or anti-drug-antibody incidence."
        ),
        residual_uncertainty=(
            # The caller understates the CQA gap below.
            "Caller states residual uncertainty is LOW after the analytical and "
            "clinical package, and that the totality of evidence supports "
            "biosimilarity."
        ),
        bridging_summary=(
            "Analytical bridging across two reference-product sourcing regions was "
            "performed to support the comparison."
        ),
        extrapolation_indications=(
            "Extrapolation to ALL reference-product indications is requested on the "
            "basis of the single studied indication plus the analytical package."
        ),
    )

    # NOTE: the afucosylation (glycosylation) level sits ABOVE the reference range,
    # which raises ADCC potency for the HIGH-risk potency CQA. Concluding
    # biosimilarity and extrapolating to all indications on this package is
    # expected to trigger a REVIEWER VETO.

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = BiosimilarComparabilityWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running BiosimilarComparabilityWorkflow...")
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
    print("BIOSIMILAR CHECKLIST:")
    for item in result.metadata["biosimilar_checklist"]:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
