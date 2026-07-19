"""
Clinical Protocol Design — worked example (veto path).

Synthetic scenario: a Phase 2 randomized trial of an investigational
drug-eluting device whose primary endpoint is a non-validated imaging surrogate,
whose sample size assumes an optimistic effect size, and whose safety plan has no
pre-specified stopping rule for a known procedural bleeding risk. The reviewer is
expected to issue a REVIEWER VETO — the protocol exposes subjects to undue risk
as designed.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/clinical_protocol_design.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.clinical_protocol_design import (
    ClinicalProtocolDesignWorkflow,
    ClinicalProtocolRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/clinical-protocol-design-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = ClinicalProtocolRequest(
        protocol_synopsis=(
            "Phase 2 randomized trial of an investigational drug-eluting device "
            "for a peripheral vascular indication."
        ),
        primary_endpoint=(
            "Change in a non-validated imaging surrogate at 6 months."
        ),
        secondary_endpoints=(
            "Target-lesion revascularization; quality-of-life score at 12 months."
        ),
        statistical_plan_summary=(
            "n=60 per arm; power assumes a large effect size that exceeds prior "
            "device data; a single interim analysis."
        ),
        population_eligibility=(
            "Adults with the indication; excludes severe comorbidity."
        ),
        safety_monitoring_plan=(
            "Investigator review at each visit; no pre-specified stopping rule "
            "for procedural bleeding."
        ),
        known_risks="Known procedural bleeding risk with the device class.",
        comparator_control="Active comparator device.",
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = ClinicalProtocolDesignWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running ClinicalProtocolDesignWorkflow...")
    print(f"Protocol: {request.protocol_synopsis[:70]}...")
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
    print("CLINICAL PROTOCOL CHECKLIST:")
    for item in result.metadata["clinical_protocol_checklist"]:
        print(f"  {item}")
    print()

    ep = result.metadata["endpoint_flags"]
    pw = result.metadata["power_flags"]
    sm = result.metadata["safety_monitoring_flags"]
    if ep or pw or sm:
        print(f"Endpoint flags ({len(ep)}): {ep}")
        print(f"Power flags ({len(pw)}): {pw}")
        print(f"Safety-monitoring flags ({len(sm)}): {sm}")


if __name__ == "__main__":
    asyncio.run(main())
