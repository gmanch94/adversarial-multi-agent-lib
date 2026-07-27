"""
RMAT Designation Eligibility Assessment — worked example (no-veto path).

Synthetic scenario (generic category, no brand): an autologous gene-modified cell
therapy for a rare inherited disorder is assessed for RMAT designation
eligibility. The reviewer is expected to flag any preliminary-evidence stretch,
overstated seriousness, or overstated unmet need rather than converge on the first
pass.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/rmat_designation.py

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
from adv_multi_agent.lifesciences.workflows.rmat_designation import (
    RMATDesignationWorkflow,
    RMATRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir=tempfile.mkdtemp(prefix="rmat-designation-example-"),
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = RMATRequest(
        product_description=(
            "An autologous gene-modified cell therapy for a rare inherited "
            "metabolic disorder."
        ),
        serious_condition_rationale=(
            "The disorder is described as serious, though many patients reach "
            "adulthood with supportive care."
        ),
        preliminary_clinical_evidence=(
            "An uncontrolled case series of 6 patients showed improvement on a "
            "biomarker surrogate at 3 months; no clinical endpoint was measured."
        ),
        unmet_medical_need=(
            "Claimed to have no available therapy, though an approved enzyme "
            "replacement exists for a subset of patients."
        ),
        intent_to_address_unmet_need=(
            "The therapy targets the genetic defect to reduce biomarker burden."
        ),
        available_therapy_landscape=(
            "An approved enzyme-replacement therapy exists for a genotype subset; "
            "supportive care otherwise."
        ),
        prior_fda_interactions=(
            "No formal FDA meeting has been held for this program."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")
    print(f"Workspace (per-run, isolated): {config.workspace_dir}")

    workflow = RMATDesignationWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running RMATDesignationWorkflow...")
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
    print("RMAT CHECKLIST:")
    for item in result.metadata["rmat_checklist"]:
        print(f"  {item}")
    print()

    ev = result.metadata["evidence_stretch_flags"]
    sc = result.metadata["serious_condition_flags"]
    un = result.metadata["unmet_need_flags"]
    if ev or sc or un:
        print(f"Evidence-stretch flags ({len(ev)}): {ev}")
        print(f"Serious-condition flags ({len(sc)}): {sc}")
        print(f"Unmet-need flags ({len(un)}): {un}")


if __name__ == "__main__":
    asyncio.run(main())
