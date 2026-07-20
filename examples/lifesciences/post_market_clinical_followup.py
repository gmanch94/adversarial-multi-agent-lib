"""
Post-Market Clinical Follow-up (PMCF) Adequacy Review — worked example (no-veto path).

Synthetic scenario: a total hip replacement implant (generic device CATEGORY —
no brand). The PMCF plan below has a DELIBERATE method gap — it relies only on
complaint-data trending for a long-term wear residual risk, with no registry or
study capturing revision rates — so the reviewer is expected to raise a
PMCF-ADEQUACY flag (and likely a RESIDUAL-RISK flag) and the workflow should NOT
converge on the first round.

Illustrative EU MDR PMCF references are scenario context, not legal or regulatory advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/post_market_clinical_followup.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.post_market_clinical_followup import (
    PMCFRequest,
    PostMarketClinicalFollowupWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/pmcf-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = PMCFRequest(
        device_description=(
            "A total hip replacement system (metal femoral head on a "
            "highly-crosslinked polyethylene liner) indicated for reconstruction "
            "of a hip joint in adults with degenerative joint disease. Class III."
        ),
        clinical_evidence_baseline=(
            "A pre-market single-arm study of 120 subjects at 2 years plus a "
            "literature review of the bearing couple. No 10-year data."
        ),
        pmcf_objectives=(
            "Confirm long-term (10-year) implant survivorship and wear "
            "performance in routine clinical use, and characterize the rate of "
            "revision for wear-related causes."
        ),
        pmcf_methods=(
            # DELIBERATE gap: complaint trending only; no registry/study.
            "Trend complaint and vigilance data by failure mode. Conduct a "
            "literature review every two years."
        ),
        residual_risks=(
            "1) Long-term polyethylene wear leading to osteolysis and revision. "
            "2) Rare adverse local tissue reaction. Both carried as residual "
            "risks requiring post-market confirmation."
        ),
        benefit_risk_baseline=(
            "Favorable at 2 years. The long-term wear risk is carried as a "
            "residual risk pending PMCF confirmation."
        ),
        data_collected_summary=(
            "18 months of complaint data show no early failure signal. The "
            "device is not enrolled in any arthroplasty registry."
        ),
        pms_linkage=(
            "Complaint trends are summarized in the annual post-market "
            "surveillance report and the periodic safety update."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = PostMarketClinicalFollowupWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running PostMarketClinicalFollowupWorkflow...")
    print(f"Device: {request.device_description[:80]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()

    print("OUTPUT:")
    print(result.output)
    print()
    print("PMCF CHECKLIST:")
    for item in result.metadata["pmcf_checklist"]:
        print(f"  {item}")
    print()

    eg = result.metadata["evidence_gap_flags"]
    rr = result.metadata["residual_risk_flags"]
    pa = result.metadata["pmcf_adequacy_flags"]
    if eg or rr or pa:
        print(f"Evidence-gap flags ({len(eg)}): {eg}")
        print(f"Residual-risk flags ({len(rr)}): {rr}")
        print(f"PMCF-adequacy flags ({len(pa)}): {pa}")


if __name__ == "__main__":
    asyncio.run(main())
