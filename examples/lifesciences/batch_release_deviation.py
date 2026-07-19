"""
Batch Release Deviation — worked example (veto path).

Synthetic scenario: an oral solid-dose tablet lot had a mid-run tablet-weight
excursion during compression, classified "minor" by the caller and proposed for
release, even though the affected interval's content-uniformity CQA was never
re-tested. The reviewer is expected to issue a REVIEWER VETO — a 'release'
disposition for a batch with an unresolved critical deviation affecting a CQA.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/batch_release_deviation.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.batch_release_deviation import (
    BatchReleaseDeviationWorkflow,
    BatchReleaseRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/batch-release-deviation-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = BatchReleaseRequest(
        batch_identifier="Oral solid-dose immediate-release tablet, lot 2026-114.",
        deviation_description=(
            "A mid-run tablet-weight excursion rose above the in-process action "
            "limit for approximately six minutes during compression before the "
            "operator corrected the feed-frame speed."
        ),
        deviation_classification="Caller proposes minor.",
        affected_cqas="Tablet weight; potentially content uniformity.",
        impact_assessment_summary=(
            "Caller states weight returned to target; content uniformity was NOT "
            "re-tested on the affected six-minute interval."
        ),
        root_cause_summary="Feed-frame speed drift; corrected mid-run.",
        capa_status="CAPA drafted to add a feed-frame interlock; not yet effective.",
        proposed_disposition="Release.",
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = BatchReleaseDeviationWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running BatchReleaseDeviationWorkflow...")
    print(f"Batch: {request.batch_identifier}")
    print(f"Proposed disposition: {request.proposed_disposition}")
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
    print("BATCH RELEASE CHECKLIST:")
    for item in result.metadata["batch_release_checklist"]:
        print(f"  {item}")
    print()

    crit = result.metadata["criticality_flags"]
    impact = result.metadata["impact_assessment_flags"]
    risk = result.metadata["release_risk_flags"]
    if crit or impact or risk:
        print(f"Criticality flags ({len(crit)}): {crit}")
        print(f"Impact-assessment flags ({len(impact)}): {impact}")
        print(f"Release-risk flags ({len(risk)}): {risk}")


if __name__ == "__main__":
    asyncio.run(main())
