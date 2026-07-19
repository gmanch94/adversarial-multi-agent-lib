"""
Substantial-Equivalence 510(k) Rationale Review — worked example (veto path).

Synthetic scenario (generic category, no brand): a blood-glucose meter is
proposed for 510(k) clearance claiming substantial equivalence to a cleared
predicate. The predicate is cleared only for professional (point-of-care) use,
but the subject device broadens the indications to OTC self-testing. No valid
predicate exists for that broadened OTC indication, so asserting substantial
equivalence would misrepresent equivalence to FDA.

The reviewer is expected to issue a REVIEWER VETO — the SE claim is
fundamentally unsupportable (near-certain Not-Substantially-Equivalent);
escalate to Regulatory Affairs and consider a De Novo pathway.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/substantial_equivalence_510k.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.substantial_equivalence_510k import (
    SubstantialEquivalence510kWorkflow,
    SERequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/se510k-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    # A blood-glucose meter claiming SE to a predicate cleared only for
    # professional use, but broadening the indication to OTC self-testing —
    # no valid predicate for the broadened indication → reviewer VETO path.
    request = SERequest(
        subject_device_description=(
            "A blood-glucose meter — a portable single-analyte photometric device "
            "with disposable amperometric test strips and a wireless data-export "
            "module, intended for glucose self-monitoring."
        ),
        intended_use=(
            "Quantitative measurement of glucose in fresh capillary whole blood to "
            "aid in the management of diabetes."
        ),
        indications_for_use=(
            "For self-testing by lay users with diabetes at home (over-the-counter) "
            "AND by healthcare professionals in point-of-care settings. The OTC "
            "self-testing indication is new relative to the cited predicate."
        ),
        technological_characteristics=(
            "Amperometric glucose-oxidase test strip, 0.5 uL capillary sample, "
            "5-second readout, on-strip hematocrit correction, Bluetooth Low Energy "
            "data export to a companion mobile application."
        ),
        candidate_predicates=(
            "A cleared blood-glucose meter of the same amperometric glucose-oxidase "
            "strip type, cleared for PROFESSIONAL point-of-care use only (not "
            "cleared for OTC lay self-testing)."
        ),
        performance_data_summary=(
            "System accuracy per ISO 15197:2013 in a professional-user hands study; "
            "99% of results within Zone A of the consensus error grid. No lay-user "
            "(OTC) accuracy or human-factors validation study was conducted."
        ),
        differences_from_predicate=(
            "Subject broadens the indication from professional-only to OTC lay "
            "self-testing, adds on-strip hematocrit correction, and adds a "
            "Bluetooth data-export module. The predicate is professional-use, "
            "display-only, without hematocrit correction."
        ),
        prior_fda_interactions=(
            "No prior 510(k) submissions or Q-Submissions for this device."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = SubstantialEquivalence510kWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running SubstantialEquivalence510kWorkflow...")
    print(f"Subject device: {request.subject_device_description[:80]}...")
    print(f"Indications: {request.indications_for_use[:80]}...")
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
    print("SE CHECKLIST:")
    for item in result.metadata["se_checklist"]:
        print(f"  {item}")
    print()

    pre = result.metadata["predicate_mismatch_flags"]
    ind = result.metadata["indication_creep_flags"]
    tec = result.metadata["technology_delta_flags"]
    if pre or ind or tec:
        print(f"Predicate-mismatch flags ({len(pre)}): {pre}")
        print(f"Indication-creep flags ({len(ind)}): {ind}")
        print(f"Technology-delta flags ({len(tec)}): {tec}")


if __name__ == "__main__":
    asyncio.run(main())
