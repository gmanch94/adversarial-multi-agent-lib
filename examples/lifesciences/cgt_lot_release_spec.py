"""
CGT Lot-Release Specification Adequacy Audit — worked example (no-veto path).

Synthetic scenario (generic category, no brand): an autologous gene-modified cell
therapy with a short shelf life proposes a lot-release specification set. The
reviewer is expected to flag any coverage / small-lot / short-shelf-life gap (e.g.
a rapid-release decision that ships before a confirmatory result without adequate
validation) rather than converge on the first pass.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/cgt_lot_release_spec.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.cgt_lot_release_spec import (
    CGTLotReleaseSpecWorkflow,
    LotReleaseSpecRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/cgt-lot-release-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = LotReleaseSpecRequest(
        product_description=(
            "An autologous gene-modified cell therapy, cryopreserved as a single "
            "patient dose."
        ),
        proposed_release_specifications=(
            "Identity by flow phenotype; purity by residual-bead count; potency by a "
            "cytotoxicity assay; sterility by a rapid method; endotoxin by LAL. NO "
            "residual replication-competent-vector safety specification is listed, "
            "and viability has no acceptance criterion."
        ),
        lot_size_and_format="Single autologous dose, ~50 mL cryobag.",
        shelf_life_and_storage="18 months at <= -150 C vapour-phase liquid nitrogen.",
        rapid_or_real_time_methods=(
            "Rapid sterility by an automated growth-based system; the product is "
            "administered under conditional release BEFORE the 14-day rapid result "
            "is final, with no documented risk justification."
        ),
        sterility_and_mycoplasma_strategy=(
            "Rapid sterility only; no mycoplasma testing strategy is described."
        ),
        out_of_specification_handling=(
            "OOS handling is not defined for a product already administered under "
            "conditional release."
        ),
        stability_program_summary=(
            "Stability supports the 18-month shelf life for potency but does not "
            "trend viability."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = CGTLotReleaseSpecWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running CGTLotReleaseSpecWorkflow...")
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
    print("LOT-RELEASE CHECKLIST:")
    for item in result.metadata["lot_release_checklist"]:
        print(f"  {item}")
    print()

    cov = result.metadata["spec_coverage_flags"]
    lot = result.metadata["small_lot_flags"]
    life = result.metadata["shelf_life_flags"]
    if cov or lot or life:
        print(f"Spec-coverage flags ({len(cov)}): {cov}")
        print(f"Small-lot flags ({len(lot)}): {lot}")
        print(f"Shelf-life flags ({len(life)}): {life}")


if __name__ == "__main__":
    asyncio.run(main())
