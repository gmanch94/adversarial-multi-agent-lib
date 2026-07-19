"""
Field-Action Classification / Recall-Class Determination — worked example
(veto path).

Synthetic scenario (generic category, no brand): a defective lot of a
point-of-care analyzer where a defect with a reasonable probability of serious
adverse health consequences (a Class I hazard) is proposed as a Class II recall,
and a reportable removal is characterised as a routine stock recovery. Under 21
CFR 806 the removal is reportable and the recall class is understated.

The reviewer is expected to issue a REVIEWER VETO — a recall-class downgrade and
a 'not reportable' call that leaves patients exposed; escalate to the Recall
committee / CQO and do not under-scope the action.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/field_action_classification.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.field_action_classification import (
    FieldActionClassificationWorkflow,
    FieldActionRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/field-action-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    # A defective lot of a point-of-care analyzer where a Class I hazard is
    # proposed as a Class II recall and a reportable removal is called a stock
    # recovery — a recall-class downgrade + non-reportable call → reviewer VETO.
    request = FieldActionRequest(
        problem_description=(
            "A calibration defect in a lot of a point-of-care analyzer under-"
            "reports a critical analyte, so a clinician can miss a value that "
            "needs urgent treatment. The complaint file proposes a Class II "
            "recall and treats the field pull as a routine stock recovery with "
            "no report required."
        ),
        health_hazard_evaluation=(
            "A missed critical value can delay urgent treatment, with a "
            "reasonable probability of serious adverse health consequences for "
            "the exposed patient population — but the file grades the hazard as "
            "low and temporary."
        ),
        affected_lots_serials=(
            "One production lot shipped to point-of-care sites, plus reagent "
            "packs cross-referenced to that lot."
        ),
        distribution_scope=(
            "Distributed to point-of-care sites across several regions; the "
            "proposed scope omits the cross-referenced reagent packs."
        ),
        action_type=(
            "Characterised as a routine stock recovery of the affected lot, "
            "logged as non-reportable, with a Class II recall proposed."
        ),
        root_cause_summary=(
            "A calibration-table error introduced at manufacture that biases "
            "the analyte result low across the affected lot."
        ),
        patient_exposure_estimate=(
            "Several thousand tests run on the affected lot before the defect "
            "was detected."
        ),
        prior_related_actions=(
            "One prior correction on the same analyte channel in an earlier lot, "
            "not reconciled with this action."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = FieldActionClassificationWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running FieldActionClassificationWorkflow...")
    print(f"Action type: {request.action_type[:80]}...")
    print(f"Problem: {request.problem_description[:80]}...")
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
    print("FIELD-ACTION CHECKLIST:")
    for item in result.metadata["field_action_checklist"]:
        print(f"  {item}")
    print()

    recall = result.metadata["recall_class_flags"]
    corr = result.metadata["correction_removal_flags"]
    hazard = result.metadata["health_hazard_flags"]
    if recall or corr or hazard:
        print(f"Recall-class flags ({len(recall)}): {recall}")
        print(f"Correction-removal flags ({len(corr)}): {corr}")
        print(f"Health-hazard flags ({len(hazard)}): {hazard}")


if __name__ == "__main__":
    asyncio.run(main())
