"""
REMS Design Review — worked example (no-veto path).

Synthetic scenario: a long-acting opioid analgesic (generic product CATEGORY —
no brand). The REMS below has a DELIBERATE assessment-plan gap — the metrics count
trained prescribers but no metric ties the assessment to the reduction in the
targeted overdose risk — so the reviewer is expected to raise an ASSESSMENT-PLAN
flag and the workflow should NOT converge on the first round.

Illustrative FDA REMS references are scenario context, not legal or regulatory advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/rems_design.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.rems_design import (
    REMSDesignRequest,
    REMSDesignWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/rems-design-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = REMSDesignRequest(
        product_description=(
            "A long-acting (extended-release) opioid analgesic indicated for "
            "severe chronic pain requiring around-the-clock treatment. Serious "
            "risks: addiction, misuse, abuse, and life-threatening overdose."
        ),
        serious_risks=(
            "1) Addiction, abuse, and misuse. 2) Life-threatening respiratory "
            "depression. 3) Accidental exposure and overdose (including in "
            "opioid-naive individuals and children)."
        ),
        rems_goals=(
            "Reduce the incidence of overdose by educating prescribers on safe "
            "prescribing and patients on safe use, storage, and disposal."
        ),
        rems_elements=(
            "Medication Guide dispensed with each prescription; prescriber "
            "communication plan (Dear-Healthcare-Provider letter); a prescriber "
            "training element on safe opioid prescribing."
        ),
        etasu_summary=(
            "Prescriber completes an accredited training module on safe opioid "
            "prescribing before certification. No pharmacy certification and no "
            "patient enrollment proposed."
        ),
        implementation_system=(
            "Training delivered through an accredited continuing-education "
            "provider; Med Guide dispensed at the pharmacy with every fill."
        ),
        assessment_plan=(
            # DELIBERATE gap: counts trained prescribers + a knowledge survey, but
            # no metric measures the reduction in the targeted overdose risk.
            "At 12 and 24 months: report the number of prescribers who completed "
            "training and survey their knowledge of safe-use messages."
        ),
        burden_assessment=(
            "The training is a one-time online module (~2 hours). No pharmacy "
            "certification, so no dispensing bottleneck and no patient access "
            "barrier."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = REMSDesignWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running REMSDesignWorkflow...")
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
    print("REMS CHECKLIST:")
    for item in result.metadata["rems_checklist"]:
        print(f"  {item}")
    print()

    rm = result.metadata["risk_mitigation_flags"]
    bu = result.metadata["burden_flags"]
    ap = result.metadata["assessment_plan_flags"]
    if rm or bu or ap:
        print(f"Risk-mitigation flags ({len(rm)}): {rm}")
        print(f"Burden flags ({len(bu)}): {bu}")
        print(f"Assessment-plan flags ({len(ap)}): {ap}")


if __name__ == "__main__":
    asyncio.run(main())
