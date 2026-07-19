"""
Computer System Validation — worked example (no-veto path).

Synthetic scenario: a cloud-hosted eQMS module (deviation + CAPA management)
claimed as GAMP Category 4, where one configurable approval-routing requirement
(URS-014) has no linked OQ test. The reviewer is expected to flag the orphan
requirement (TRACE-GAP) until the executor's review names it against the trace
matrix and calls for the missing test.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/computer_system_validation.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.computer_system_validation import (
    ComputerSystemValidationRequest,
    ComputerSystemValidationWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/computer-system-validation-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = ComputerSystemValidationRequest(
        system_description=(
            "Cloud-hosted eQMS module managing deviations and CAPA records for a "
            "GMP manufacturing site."
        ),
        intended_use_statement=(
            "Manage GxP deviation and CAPA records with electronic signatures "
            "under 21 CFR Part 11 / EU Annex 11."
        ),
        gamp_category="Caller claims GAMP Category 4 (configured product).",
        requirements_summary=(
            "URS-010 electronic signature; URS-012 audit trail; URS-014 "
            "configurable approval routing; URS-016 role-based access model."
        ),
        risk_assessment_summary=(
            "High patient-impact for CAPA effectiveness; medium for routing "
            "configuration; low for cosmetic UI."
        ),
        test_evidence_summary=(
            "OQ-010 e-signature executed and approved; OQ-012 audit trail "
            "executed; PQ-001 end-to-end executed. No OQ referenced for routing."
        ),
        trace_matrix_summary=(
            "URS-010 -> OQ-010; URS-012 -> OQ-012; URS-014 unlinked; "
            "URS-016 -> PQ-001."
        ),
        change_control_summary=(
            "Validated state held under change control CC-2026-031."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = ComputerSystemValidationWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running ComputerSystemValidationWorkflow...")
    print(f"System: {request.system_description[:70]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()
    print("OUTPUT:")
    print(result.output)
    print()
    print("CSV CHECKLIST:")
    for item in result.metadata["csv_checklist"]:
        print(f"  {item}")
    print()

    iu = result.metadata["intended_use_flags"]
    tg = result.metadata["trace_gap_flags"]
    te = result.metadata["test_evidence_flags"]
    if iu or tg or te:
        print(f"Intended-use flags ({len(iu)}): {iu}")
        print(f"Trace-gap flags ({len(tg)}): {tg}")
        print(f"Test-evidence flags ({len(te)}): {te}")


if __name__ == "__main__":
    asyncio.run(main())
