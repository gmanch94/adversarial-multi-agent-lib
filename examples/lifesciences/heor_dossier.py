"""
HEOR Value Dossier Review — worked example (no-veto path).

Synthetic scenario: an oncology therapy value dossier (generic product CATEGORY —
no brand). The dossier has a DELIBERATE comparator problem — the comparator is no
longer standard of care — plus a surrogate endpoint (PFS) driving a lifetime model
with optimistic survival extrapolation, so the reviewer is expected to raise
COMPARATOR (and likely ENDPOINT-RELEVANCE / EXTRAPOLATION) flags and the workflow
should NOT converge on the first round.

Illustrative HTA / payer references are scenario context, not legal or medical advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/heor_dossier.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.heor_dossier import (
    HEORDossierRequest,
    HEORDossierWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/heor-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = HEORDossierRequest(
        product_description=(
            "A targeted oncology therapy for a solid-tumor indication, seeking "
            "reimbursement across a national market."
        ),
        value_proposition=(
            "Claims improved progression-free survival and a favorable "
            "cost-per-quality-adjusted-life-year versus current therapy."
        ),
        comparators=(
            # DELIBERATE: outdated comparator.
            "The economic comparison is drawn against a chemotherapy regimen that "
            "was standard of care several years ago but has since been displaced "
            "by a newer first-line therapy in the target market."
        ),
        clinical_evidence_summary=(
            "A single open-label pivotal trial with progression-free survival as "
            "the primary endpoint; overall-survival data remain immature."
        ),
        economic_model_summary=(
            "A lifetime partitioned-survival cost-effectiveness model whose key "
            "driver is the progression-free-survival benefit, with a time horizon "
            "far beyond the trial follow-up."
        ),
        endpoints_used=(
            # DELIBERATE: surrogate endpoint in place of a final endpoint.
            "Progression-free survival is used as the value driver (a surrogate); "
            "overall survival, the patient-relevant final endpoint, is immature "
            "and not used."
        ),
        extrapolation_assumptions=(
            # DELIBERATE: optimistic extrapolation.
            "Long-term survival is extrapolated using an optimistic parametric "
            "curve fitted to the immature data, assuming the PFS benefit fully "
            "translates into an overall-survival benefit."
        ),
        target_audience=(
            "A national health-technology-assessment body and hospital formulary "
            "committees."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = HEORDossierWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running HEORDossierWorkflow...")
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
    print("HEOR CHECKLIST:")
    for item in result.metadata["heor_checklist"]:
        print(f"  {item}")
    print()

    co = result.metadata["comparator_flags"]
    en = result.metadata["endpoint_relevance_flags"]
    ex = result.metadata["extrapolation_flags"]
    if co or en or ex:
        print(f"Comparator flags ({len(co)}): {co}")
        print(f"Endpoint-relevance flags ({len(en)}): {en}")
        print(f"Extrapolation flags ({len(ex)}): {ex}")


if __name__ == "__main__":
    asyncio.run(main())
