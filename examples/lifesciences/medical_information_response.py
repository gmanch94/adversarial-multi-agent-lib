"""
Medical Information Response Review — worked example (VETO path).

Synthetic scenario: an approved oral therapy (generic product CATEGORY — no brand)
where an HCP asks, unsolicited, about an off-label pediatric dose. The DRAFTED
response RECOMMENDS the off-label regimen rather than neutrally summarizing the
evidence and its limitations — so the reviewer is expected to VETO (a response
that promotes an off-label use).

BOUNDARY (D-LIFESCI-2): distinct from PromotionalOffLabelReviewWorkflow (proactive
promotion, off-label prohibited). This is a REACTIVE response to an unsolicited
inquiry, where balanced off-label scientific exchange is permitted and only
PROMOTION of an off-label use is vetoed.

Illustrative FDA medical-information / unsolicited-request references are scenario
context, not legal or medical advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/medical_information_response.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.medical_information_response import (
    MedicalInfoRequest,
    MedicalInformationResponseWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/medinfo-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = MedicalInfoRequest(
        product_description=(
            "An approved oral small-molecule therapy indicated for an adult "
            "condition. Pediatric use is not in the approved label."
        ),
        inquiry_summary=(
            "A treating physician asks, unsolicited, what dose of the product "
            "they should use in an adolescent patient who has exhausted labeled "
            "options (an off-label population)."
        ),
        inquiry_source="Unsolicited telephone inquiry from a treating physician.",
        on_off_label_status=(
            "Off-label: the pediatric/adolescent population is not covered by the "
            "approved indication or dosing."
        ),
        proposed_response=(
            # DELIBERATE: the response promotes an off-label regimen.
            "The drafted response RECOMMENDS a specific weight-based adolescent "
            "dosing regimen and states the product 'should be used' in this "
            "population, rather than neutrally summarizing the limited available "
            "evidence and its uncertainties."
        ),
        evidence_cited=(
            "Two small observational case series and a narrative review; no "
            "controlled pediatric trial exists."
        ),
        balance_summary=(
            "The draft mentions efficacy signals but underplays the known hepatic "
            "risk and the absence of controlled pediatric safety data."
        ),
        promotional_review_status=(
            "Drafted by a call-center agent; not yet reviewed by MLR; intended to "
            "be reactive but reads as a recommendation."
        ),
    )

    # NOTE: a medical-information response may DISCUSS off-label evidence when
    # unsolicited, but RECOMMENDING an off-label regimen crosses into promotion of
    # an unapproved use and is expected to trigger a REVIEWER VETO.

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = MedicalInformationResponseWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running MedicalInformationResponseWorkflow...")
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
    print("MEDICAL-INFORMATION CHECKLIST:")
    for item in result.metadata["medinfo_checklist"]:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
