"""
Device Reportability / MDR Determination — worked example (veto path).

Synthetic scenario (generic category, no brand): a complaint on an infusion pump
where a patient required an unplanned intervention (a reportable serious injury)
is coded as a minor, non-reportable event, and a recurring occlusion malfunction —
seen in several prior events — is ignored rather than assessed against the trend
reporting trigger. Under 21 CFR 803 the event is reportable and the statutory
clock is running.

The reviewer is expected to issue a REVIEWER VETO — a 'non-reportable'
determination that is actually reportable under the applicable regulation;
escalate to the Vigilance officer and initiate the report within the statutory
clock.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/device_reportability.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.device_reportability import (
    DeviceReportabilityWorkflow,
    ReportabilityRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/device-reportability-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    # An infusion-pump complaint where a reportable serious injury is coded
    # non-reportable and a recurring occlusion malfunction trend is ignored —
    # a 'non-reportable' call that is actually reportable → reviewer VETO path.
    request = ReportabilityRequest(
        complaint_narrative=(
            "A user reported that an infusion pump failed to deliver a scheduled "
            "dose because of an occlusion the alarm did not catch. The patient "
            "deteriorated and required an unplanned clinical intervention to "
            "recover. The complaint file codes the event as a minor device "
            "malfunction with no report required."
        ),
        device_identifier=(
            "An infusion pump (large-volume, general-ward class), single model line."
        ),
        event_outcome=(
            "The patient required an unplanned intervention (rescue therapy) and "
            "was stabilised; the outcome met the threshold for a serious injury."
        ),
        patient_impact=(
            "Graded in the complaint file as 'minor, non-serious' despite the "
            "unplanned intervention that was required to prevent lasting harm."
        ),
        malfunction_recurrence_potential=(
            "The occlusion-detection fault can recur on the deployed fleet and, if "
            "it does, is likely to cause or contribute to a serious injury."
        ),
        prior_similar_events_count=(
            "Six prior similar occlusion-detection complaints over the trailing "
            "twelve months across the same model line — a rising trend."
        ),
        market_regions="United States and European Union.",
        date_became_aware=(
            "The manufacturer became aware of this event on the complaint-intake "
            "date; the statutory clock is running from that date."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = DeviceReportabilityWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running DeviceReportabilityWorkflow...")
    print(f"Device identifier: {request.device_identifier[:80]}...")
    print(f"Event outcome: {request.event_outcome[:80]}...")
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
    print("REPORTABILITY CHECKLIST:")
    for item in result.metadata["reportability_checklist"]:
        print(f"  {item}")
    print()

    rep = result.metadata["reportability_flags"]
    inj = result.metadata["serious_injury_flags"]
    trend = result.metadata["malfunction_trend_flags"]
    if rep or inj or trend:
        print(f"Reportability flags ({len(rep)}): {rep}")
        print(f"Serious-injury flags ({len(inj)}): {inj}")
        print(f"Malfunction-trend flags ({len(trend)}): {trend}")


if __name__ == "__main__":
    asyncio.run(main())
