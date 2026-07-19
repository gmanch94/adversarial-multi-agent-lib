"""
CMO / CDMO Qualification — worked example (no-veto path).

Synthetic scenario: a sterile fill-finish CDMO proposed for a new commercial
aseptic vial product, carrying two prior major audit observations (one still an
open CAPA on environmental monitoring) and high existing utilization. The
reviewer is expected to flag the open GMP CAPA (GMP-GAP) and the capacity gap
(CAPACITY) until the executor's review addresses both against the evidence.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/cmo_qualification.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.cmo_qualification import (
    CMOQualificationRequest,
    CMOQualificationWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/cmo-qualification-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = CMOQualificationRequest(
        supplier_description=(
            "A sterile fill-finish CDMO proposed for a new commercial aseptic "
            "vial product."
        ),
        audit_findings_summary=(
            "Last audit produced two major observations: environmental "
            "monitoring excursions and gowning qualification gaps."
        ),
        gmp_history=(
            "One prior regulatory inspection closed with voluntary corrections; "
            "no warning letter on file."
        ),
        data_integrity_posture=(
            "Audit trails reviewed on the fill line; segregation of duties in "
            "place; no shared logins reported."
        ),
        capacity_assessment=(
            "Declares two aseptic lines; utilization is already high on existing "
            "committed volumes."
        ),
        quality_agreement_status="Quality agreement in draft; not yet executed.",
        capa_status=(
            "Open CAPA on environmental monitoring; gowning-qualification CAPA "
            "closed and verified."
        ),
        technical_transfer_readiness=(
            "Process validation protocol drafted; not yet executed at the CDMO."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = CMOQualificationWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running CMOQualificationWorkflow...")
    print(f"Supplier: {request.supplier_description[:70]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()
    print("OUTPUT:")
    print(result.output)
    print()
    print("CMO QUALIFICATION CHECKLIST:")
    for item in result.metadata["cmo_checklist"]:
        print(f"  {item}")
    print()

    gmp = result.metadata["gmp_gap_flags"]
    di = result.metadata["data_integrity_flags"]
    cap = result.metadata["capacity_flags"]
    if gmp or di or cap:
        print(f"GMP-gap flags ({len(gmp)}): {gmp}")
        print(f"Data-integrity flags ({len(di)}): {di}")
        print(f"Capacity flags ({len(cap)}): {cap}")


if __name__ == "__main__":
    asyncio.run(main())
