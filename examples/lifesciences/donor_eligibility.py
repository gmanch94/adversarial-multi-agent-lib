"""
Donor-Eligibility Determination Review — worked example (veto path).

Synthetic scenario (generic category, no brand): an allogeneic living-donor
product is proposed as eligible, but a required communicable-disease test is
reactive and no eligibility exception applies. Releasing the product would risk
communicable-disease transmission.

The reviewer is expected to issue a REVIEWER VETO — do not release.

Note (L-HEALTH-1): donor screening / testing fields can echo individually
identifiable donor data; a real deployment must apply downstream PHI handling.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/donor_eligibility.py

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
from adv_multi_agent.lifesciences.workflows.donor_eligibility import (
    DonorEligibilityWorkflow,
    DonorEligibilityRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir=tempfile.mkdtemp(prefix="donor-eligibility-example-"),
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = DonorEligibilityRequest(
        donation_type="Allogeneic living donor.",
        donor_screening_summary=(
            "Risk-factor history completed; no self-reported risk factors; physical "
            "assessment unremarkable."
        ),
        donor_testing_summary=(
            "Testing for the relevant communicable-disease agents was performed; ONE "
            "required agent returned a REACTIVE result on the required method."
        ),
        agents_considered=(
            "The relevant communicable-disease agents required for a living donor "
            "were considered."
        ),
        plasma_dilution_assessment=(
            "Plasma dilution within limit; does not explain the reactive result."
        ),
        physical_assessment_or_records_review=(
            "Records review did not surface an eligibility exception for a reactive "
            "result."
        ),
        retesting_or_repeat_status=(
            "No confirmatory retesting resolving the reactive result is documented."
        ),
        urgent_medical_need_flag=(
            "The determination is proposed as ROUTINE eligibility, not an urgent-need "
            "path, despite the reactive result."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")
    print(f"Workspace (per-run, isolated): {config.workspace_dir}")

    workflow = DonorEligibilityWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running DonorEligibilityWorkflow...")
    print(f"Donation type: {request.donation_type}")
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
    print("DONOR CHECKLIST:")
    for item in result.metadata["donor_checklist"]:
        print(f"  {item}")
    print()

    sc = result.metadata["screening_gap_flags"]
    te = result.metadata["testing_gap_flags"]
    ir = result.metadata["ineligible_release_flags"]
    if sc or te or ir:
        print(f"Screening-gap flags ({len(sc)}): {sc}")
        print(f"Testing-gap flags ({len(te)}): {te}")
        print(f"Ineligible-release flags ({len(ir)}): {ir}")


if __name__ == "__main__":
    asyncio.run(main())
