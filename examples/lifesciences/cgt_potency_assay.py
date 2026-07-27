"""
CGT Potency-Assay Lot-Release Adequacy Review — worked example (veto path).

Synthetic scenario (generic category, no brand): an autologous CAR-T therapy
proposes to release lots on a total-viable-cell readout that does not measure
antigen-specific killing — the mechanism of action. Because the assay does not
measure clinical activity, releasing on it risks releasing product without
demonstrated potency.

The reviewer is expected to issue a REVIEWER VETO — requalify with an MoA-linked
potency assay before release.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/cgt_potency_assay.py

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
from adv_multi_agent.lifesciences.workflows.cgt_potency_assay import (
    CGTPotencyAssayWorkflow,
    PotencyAssayRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir=tempfile.mkdtemp(prefix="cgt-potency-example-"),
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = PotencyAssayRequest(
        product_description="An autologous CAR-T cell therapy.",
        mechanism_of_action=(
            "CAR-mediated recognition of a tumour-associated antigen driving T-cell "
            "cytotoxicity and cytokine release."
        ),
        potency_assay_description=(
            "A total-viable-cell count with a flow-cytometry viability readout. No "
            "antigen-specific killing or cytokine-release readout is included."
        ),
        moa_linkage_rationale=(
            "Asserted that viable cell number correlates with potency, without data "
            "linking viability to antigen-specific killing."
        ),
        assay_validation_summary=(
            "Validated for precision and range as a cell-count method; no "
            "specificity to the killing mechanism was established."
        ),
        acceptance_criteria="Viable cell count >= the target dose.",
        lot_release_claim="The product meets the potency specification for release.",
        surrogate_or_matrix_justification=(
            "Viability is used as a surrogate for potency with no bridging data to "
            "the cytotoxic mechanism."
        ),
        stability_indicating_evidence=(
            "Viability declines on storage but is not shown to track loss of "
            "antigen-specific killing."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")
    print(f"Workspace (per-run, isolated): {config.workspace_dir}")

    workflow = CGTPotencyAssayWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running CGTPotencyAssayWorkflow...")
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
    print("POTENCY CHECKLIST:")
    for item in result.metadata["potency_checklist"]:
        print(f"  {item}")
    print()

    moa = result.metadata["moa_linkage_flags"]
    claim = result.metadata["lot_release_claim_flags"]
    val = result.metadata["assay_validation_flags"]
    if moa or claim or val:
        print(f"MoA-linkage flags ({len(moa)}): {moa}")
        print(f"Lot-release-claim flags ({len(claim)}): {claim}")
        print(f"Assay-validation flags ({len(val)}): {val}")


if __name__ == "__main__":
    asyncio.run(main())
