"""
Viral-Vector Genome-Safety Characterisation Audit — worked example (no-veto path).

Synthetic scenario (generic category, no brand): a third-generation
self-inactivating lentiviral vector for an ex-vivo gene-modified cell therapy is
audited for genome-safety characterisation adequacy — RCR/RCL testing,
integration profile, insertional-mutagenesis, and oncogenicity. The reviewer is
expected to flag any characterisation gap (e.g. RCL sampling too small for the
vector class) rather than converge on the first pass.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/vector_safety.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.vector_safety import (
    VectorSafetyWorkflow,
    VectorSafetyRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/vector-safety-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = VectorSafetyRequest(
        vector_description=(
            "A third-generation self-inactivating (SIN) lentiviral vector encoding "
            "a chimeric antigen receptor, used for ex-vivo modification of autologous "
            "T cells."
        ),
        rcr_rcl_testing_summary=(
            "RCL testing by co-culture amplification with a PCR endpoint on "
            "end-of-production cells only; a 1% cell-equivalent sample was assayed. "
            "Vector supernatant was NOT independently tested."
        ),
        integration_profile_data=(
            "Integration-site analysis by LAM-PCR on the final drug product shows a "
            "polyclonal distribution with no dominant clone above the reporting "
            "threshold."
        ),
        insertional_mutagenesis_assessment=(
            "Risk described as low on the basis of the SIN design; no clonal-expansion "
            "monitoring commitment is stated in the follow-up plan."
        ),
        oncogenicity_or_tumorigenicity_data=(
            "An in-vitro immortalisation assay was negative; no in-vivo tumorigenicity "
            "study was performed."
        ),
        vector_copy_number=(
            "Mean vector copy number 3.4 per cell; acceptance criterion <= 5 per cell."
        ),
        nonclinical_biodistribution=(
            "Biodistribution in the animal model showed transient signal limited to "
            "lymphoid tissue, largely cleared by day 90."
        ),
        long_term_followup_plan=(
            "A 5-year follow-up is proposed (shorter than the 15 years typical for an "
            "integrating vector); periodic RCL monitoring is not committed."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = VectorSafetyWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running VectorSafetyWorkflow...")
    print(f"Vector: {request.vector_description[:80]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()
    print("OUTPUT:")
    print(result.output)
    print()
    print("VECTOR-SAFETY CHECKLIST:")
    for item in result.metadata["vector_safety_checklist"]:
        print(f"  {item}")
    print()

    rcr = result.metadata["rcr_rcl_risk_flags"]
    ins = result.metadata["insertional_mutagenesis_flags"]
    onc = result.metadata["oncogenicity_flags"]
    if rcr or ins or onc:
        print(f"RCR/RCL-risk flags ({len(rcr)}): {rcr}")
        print(f"Insertional-mutagenesis flags ({len(ins)}): {ins}")
        print(f"Oncogenicity flags ({len(onc)}): {onc}")


if __name__ == "__main__":
    asyncio.run(main())
