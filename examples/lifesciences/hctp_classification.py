"""
HCT/P Regulatory-Tier Classification Review — worked example (veto path).

Synthetic scenario (generic category, no brand): a minimally-processed
structural-tissue product is proposed as a 361 HCT/P, but the actual process
expands and formulates the cells for a metabolic systemic effect and a
non-homologous use — which makes it a 351 biologic requiring a BLA. Asserting the
361 tier would bypass the BLA and misrepresent regulatory status.

(Per D-LIFESCI-7 scenario scoping, the 361 argument is only live for
minimally-manipulated cellular / structural-tissue products; genetically-modified
and viral-vector products are categorically 351 and are not used here.)

The reviewer is expected to issue a REVIEWER VETO — pursue the BLA pathway.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/hctp_classification.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os
import tempfile

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.hctp_classification import (
    HCTPClassificationWorkflow,
    HCTPClassificationRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir=tempfile.mkdtemp(prefix="hctp-classification-example-"),
        max_review_rounds=3,
        score_threshold=8.0,
    )

    request = HCTPClassificationRequest(
        product_description=(
            "A processed adipose-derived cell preparation proposed as a 361 HCT/P "
            "for a metabolic indication."
        ),
        cellular_tissue_source="Autologous adipose tissue.",
        manufacturing_steps=(
            "Enzymatic digestion, culture EXPANSION over multiple passages, and "
            "formulation for intravenous infusion."
        ),
        minimal_manipulation_rationale=(
            "Claimed minimal because the cells are 'the patient's own', ignoring the "
            "culture expansion that alters the relevant biological characteristics."
        ),
        intended_use_homology=(
            "Intended for a systemic metabolic effect — NOT the original structural / "
            "cushioning function of adipose tissue (non-homologous)."
        ),
        combination_with_another_article="Formulated with a proprietary growth additive.",
        systemic_effect_or_metabolic_dependence=(
            "Intended to exert a systemic metabolic effect dependent on the living "
            "cells' metabolic activity after infusion."
        ),
        proposed_regulatory_tier="Proposed as a 361 HCT/P.",
        precedent_determinations=(
            "Comparable culture-expanded, systemically-administered cell products "
            "have been regulated as 351 biologics."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")
    print(f"Workspace (per-run, isolated): {config.workspace_dir}")

    workflow = HCTPClassificationWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running HCTPClassificationWorkflow...")
    print(f"Product: {request.product_description[:80]}...")
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
    print("HCT/P CHECKLIST:")
    for item in result.metadata["hctp_checklist"]:
        print(f"  {item}")
    print()

    mm = result.metadata["minimal_manipulation_flags"]
    hu = result.metadata["homologous_use_flags"]
    tier = result.metadata["tier_classification_flags"]
    if mm or hu or tier:
        print(f"Minimal-manipulation flags ({len(mm)}): {mm}")
        print(f"Homologous-use flags ({len(hu)}): {hu}")
        print(f"Tier-classification flags ({len(tier)}): {tier}")


if __name__ == "__main__":
    asyncio.run(main())
