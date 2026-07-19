"""
Nutrition Health-Claim Review — worked example (no-veto path).

Synthetic scenario: an adult nutritional shake (generic product CATEGORY — no
brand) carrying a structure-function claim, plus an infant-formula nutrient-
adequacy angle. The label-claim package below carries one DELIBERATE undeclared
major allergen (milk protein is in the formulation but only soy is declared), so
the reviewer is expected to raise an ALLERGEN flag and the workflow should NOT
converge on the first round.

Illustrative FDA references (structure-function-claim substantiation, 21 CFR 107
infant-formula nutrient minimums, major-allergen declaration) are scenario
context, not legal or regulatory advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/nutrition_health_claim.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.nutrition_health_claim import (
    NutritionClaimRequest,
    NutritionHealthClaimWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/nutrition-claim-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    # Adult nutritional shake label-claim package. The formulation contains milk
    # protein but the allergen declaration lists only soy → reviewer should raise
    # an ALLERGEN flag (undeclared major allergen: milk).
    request = NutritionClaimRequest(
        product_category=(
            "Adult nutritional shake: a ready-to-drink oral nutritional "
            "supplement for adults, sold as a complete-nutrition beverage. A "
            "line-extension of the same base formula is positioned separately as "
            "an infant formula subject to 21 CFR 107 nutrient minimums."
        ),
        claim_set=(
            "C-01: 'Supports muscle health' (structure-function claim). "
            "C-02: 'Excellent source of protein' (nutrient-content claim). "
            "C-03: 'Complete, balanced nutrition' (nutrient-content claim). "
            "C-04 (infant-formula line): 'Supports healthy growth and "
            "development' (structure-function claim)."
        ),
        substantiation_dossier_summary=(
            "D-01: Randomised controlled trial linking the C-01 protein-plus-"
            "leucine blend to preserved lean muscle mass in adults (supports "
            "C-01). "
            "D-02: Certificate-of-analysis nutrient panel (supports C-02, C-03). "
            "D-04: For the infant-formula line, only a marketing dossier is "
            "cited for C-04 — no competent-reliable growth study is attached "
            "(C-04 substantiation is INCOMPLETE)."
        ),
        target_population=(
            "Primary: adults 19+ using the shake as an oral nutritional "
            "supplement. Secondary line: infants 0–12 months (infant-formula "
            "line extension, 21 CFR 107 applies)."
        ),
        nutrient_profile=(
            "Adult shake per 8 fl oz: 350 kcal, 30 g protein, 25 vitamins and "
            "minerals at 20–50% DV. "
            "Infant-formula line per 100 kcal: energy and macronutrients within "
            "range, but the iron level as summarised is below the 21 CFR 107 "
            "infant-formula minimum (nutrient-adequacy gap to verify)."
        ),
        allergen_declaration=(
            "Declared 'Contains: soy.' Manufactured on lines shared with other "
            "products. NOTE: the base formula includes milk protein concentrate, "
            "but milk is NOT listed in the Contains statement (deliberate "
            "undeclared major allergen)."
        ),
        infant_formula_flag=(
            "Yes — a line extension is an infant formula subject to 21 CFR 107 "
            "nutrient minimums and the associated quality-factor requirements."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = NutritionHealthClaimWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running NutritionHealthClaimWorkflow...")
    print(f"Product: {request.product_category[:80]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()

    print("OUTPUT:")
    print(result.output)
    print()
    print("NUTRITION CHECKLIST:")
    for item in result.metadata["nutrition_checklist"]:
        print(f"  {item}")
    print()

    sub = result.metadata["claim_substantiation_flags"]
    nut = result.metadata["nutrient_adequacy_flags"]
    alg = result.metadata["allergen_flags"]
    if sub or nut or alg:
        print(f"Claim-substantiation flags ({len(sub)}): {sub}")
        print(f"Nutrient-adequacy flags ({len(nut)}): {nut}")
        print(f"Allergen flags ({len(alg)}): {alg}")


if __name__ == "__main__":
    asyncio.run(main())
