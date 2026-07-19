"""
Combination-Product PMOA Routing — worked example (no-veto path).

Synthetic scenario: a prefilled single-dose autoinjector delivering a biologic
(generic product CATEGORY — no brand). It is a two-constituent combination
product: a therapeutic biologic (the constituent providing the primary
therapeutic effect) plus a single-use autoinjector device (delivery only). The
package below carries a DELIBERATE routing error — the caller proposes CDRH as
the lead center even though the biologic provides the primary mode of action —
so the reviewer is expected to raise a LEAD-CENTER flag and the workflow should
NOT converge on the first round.

Illustrative FDA references (21 CFR 3 primary-mode-of-action determination,
CDER / CBER / CDRH lead-center assignment, NDA / BLA / PMA / 510(k) pathways)
are scenario context, not legal or regulatory advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/combination_product_pmoa.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.combination_product_pmoa import (
    CombinationProductPMOAWorkflow,
    PMOARequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/pmoa-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    # Prefilled single-dose autoinjector delivering a biologic. The biologic
    # provides the primary therapeutic effect (biologic PMOA → CBER lead center),
    # but the caller proposes CDRH → reviewer should raise a LEAD-CENTER flag
    # (proposed center inconsistent with the biologic PMOA).
    request = PMOARequest(
        product_description=(
            "A prefilled single-dose autoinjector that delivers a therapeutic "
            "biologic subcutaneously. Sold as a single combination product: the "
            "biologic and the injector are co-packaged and used together as a "
            "unit (generic product CATEGORY, no brand)."
        ),
        constituent_parts=(
            "Constituent A: a therapeutic biologic (a monoclonal-antibody-class "
            "biological product). "
            "Constituent B: a single-use spring-driven autoinjector device that "
            "delivers a fixed subcutaneous dose."
        ),
        therapeutic_effect_mechanism=(
            "The biologic binds its target and produces the intended therapeutic "
            "effect. The autoinjector performs mechanical delivery of a fixed "
            "dose but has no independent therapeutic action of its own."
        ),
        each_constituent_contribution=(
            "Biologic: provides the PRIMARY therapeutic action (target binding "
            "and downstream effect). "
            "Device: delivery and dose-accuracy only — no therapeutic effect; it "
            "does not act on the disease pathway."
        ),
        proposed_pmoa=(
            "Caller proposes a BIOLOGIC primary mode of action — the biologic "
            "provides the most important therapeutic action; the device only "
            "delivers it."
        ),
        proposed_lead_center=(
            "Caller proposes CDRH as the lead center (DELIBERATE error: CDRH is "
            "the devices center, which does not follow from a biologic PMOA — a "
            "biologic PMOA routes to CBER)."
        ),
        precedent_products=(
            "Prior prefilled / single-dose biologic-delivery combination products "
            "in which the biologic provided the primary mode of action and the "
            "delivery device was a constituent part, routed to the biologics "
            "center."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = CombinationProductPMOAWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running CombinationProductPMOAWorkflow...")
    print(f"Product: {request.product_description[:80]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()

    print("OUTPUT:")
    print(result.output)
    print()
    print("PMOA CHECKLIST:")
    for item in result.metadata["pmoa_checklist"]:
        print(f"  {item}")
    print()

    pmoa = result.metadata["pmoa_flags"]
    center = result.metadata["lead_center_flags"]
    pathway = result.metadata["pathway_flags"]
    if pmoa or center or pathway:
        print(f"PMOA flags ({len(pmoa)}): {pmoa}")
        print(f"Lead-center flags ({len(center)}): {center}")
        print(f"Pathway flags ({len(pathway)}): {pathway}")


if __name__ == "__main__":
    asyncio.run(main())
