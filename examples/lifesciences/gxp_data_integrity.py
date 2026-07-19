"""
GxP Data Integrity — worked example (no-veto path).

Synthetic scenario: a chromatography data system (CDS) on a QC lab bench
supporting GMP release testing. The audit trail is enabled and tamper-evident
but is not part of the routine review-by-exception checklist, and one shared
login is retained for a legacy instrument. The reviewer is expected to flag the
audit-trail-review gap (AUDIT-TRAIL) and the shared-login attribution failure
(ATTRIBUTION) until the executor's assessment names both against the evidence.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/gxp_data_integrity.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.gxp_data_integrity import (
    GxPDataIntegrityRequest,
    GxPDataIntegrityWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/gxp-data-integrity-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = GxPDataIntegrityRequest(
        system_description=(
            "Chromatography data system (CDS) on a QC lab bench supporting GMP "
            "release testing of a finished oral solid-dose product."
        ),
        record_type=(
            "Hybrid: electronic chromatograms retained in the CDS with paper "
            "result printouts countersigned by the analyst and reviewer."
        ),
        audit_trail_summary=(
            "The CDS audit trail is enabled and tamper-evident. It is available "
            "on demand but is NOT part of the routine review-by-exception "
            "checklist performed at result review."
        ),
        access_control_summary=(
            "Named analyst logins for the current instruments. One shared login "
            "('lab-legacy') is retained for a legacy HPLC that predates SSO."
        ),
        data_lifecycle_summary=(
            "Create -> process -> review -> report -> archive on validated "
            "network storage with a 10-year retention policy."
        ),
        alcoa_assessment=(
            "Caller asserts all ALCOA+ attributes are met. Contemporaneous "
            "recording is not separately evidenced for the legacy instrument."
        ),
        deviations_investigations=(
            "One prior integration-parameter deviation (2025); CAPA closed with "
            "an SOP update. No open data-integrity investigations."
        ),
        review_by_exception_summary=(
            "Review by exception covers integration changes but does not extend "
            "to audit-trail entries or login events."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = GxPDataIntegrityWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running GxPDataIntegrityWorkflow...")
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
    print("GxP DATA-INTEGRITY CHECKLIST:")
    for item in result.metadata["gxp_checklist"]:
        print(f"  {item}")
    print()

    alcoa = result.metadata["alcoa_flags"]
    audit = result.metadata["audit_trail_flags"]
    attr = result.metadata["attribution_flags"]
    if alcoa or audit or attr:
        print(f"ALCOA flags ({len(alcoa)}): {alcoa}")
        print(f"Audit-trail flags ({len(audit)}): {audit}")
        print(f"Attribution flags ({len(attr)}): {attr}")


if __name__ == "__main__":
    asyncio.run(main())
