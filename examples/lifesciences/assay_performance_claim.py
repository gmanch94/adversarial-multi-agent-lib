"""
Assay Performance-Claim Review — worked example (veto path).

Synthetic scenario (generic category, no brand): a rapid antigen test
(lateral-flow immunoassay) proposes a 99% sensitivity claim for symptomatic
nasal-swab use. The clinical study (n=180, RT-PCR reference, CLSI EP12) has a
lower 95% CI bound of only ~94%, so the 99% point-estimate claim is not
supported by the data. Releasing it would risk false-negative misdiagnosis and
an adulteration/misbranding exposure.

The reviewer is expected to issue a REVIEWER VETO — the claim the study data
cannot support must not be released; escalate to Diagnostics Regulatory.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/assay_performance_claim.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.assay_performance_claim import (
    AssayPerformanceClaimWorkflow,
    AssayClaimRequest,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/assay-claim-example",
        max_review_rounds=3,
        score_threshold=8.0,
    )

    # A rapid antigen test claiming 99% sensitivity where the clinical study
    # (n=180) supports only a ~94% lower CI bound → reviewer VETO path.
    request = AssayClaimRequest(
        assay_description=(
            "A rapid antigen test — single-use lateral-flow immunoassay cassette "
            "with a visual line-intensity readout, intended for point-of-care use."
        ),
        intended_use=(
            "Qualitative detection of a viral nucleoprotein antigen in direct "
            "nasal-swab specimens from individuals suspected of acute respiratory "
            "infection within the first 5 days of symptom onset. Point-of-care and "
            "near-patient settings."
        ),
        analyte_measurand=(
            "Viral nucleoprotein antigen. Sandwich immunoassay; gold-conjugate "
            "detection with a qualitative visual line readout scored positive / "
            "negative against a reference card."
        ),
        claim_set=(
            "Proposed labeling claims: clinical sensitivity 99% (nasal swab, "
            "symptomatic); clinical specificity 98.5%; limit of detection "
            "1.2 x 10^2 TCID50/mL; shelf life 24 months at 2–30°C; usable with "
            "both nasal-swab and saliva specimens."
        ),
        study_design_summary=(
            "Prospective multi-site clinical study, n=180 RT-PCR-positive and "
            "620 RT-PCR-negative symptomatic subjects. RT-PCR reference method. "
            "CLSI EP12 qualitative protocol. Observed positive percent agreement "
            "96.1% (95% CI 92.4–98.3%); lower bound ~94% after site adjustment. "
            "No pediatric subjects enrolled."
        ),
        interference_panel_tested=(
            "Nasal-swab matrix: mucin, whole blood, common OTC nasal sprays, "
            "menthol, and nasal corticosteroids tested per CLSI EP07 — no "
            "interference at stated concentrations. Saliva matrix was NOT included "
            "in the interference panel."
        ),
        cross_reactivity_data=(
            "Tested against 18 respiratory pathogens and 4 common commensals; no "
            "cross-reactivity observed at the tested titers. High-dose hook effect "
            "not evaluated."
        ),
        stability_claims=(
            "24-month shelf life supported by accelerated stability plus 18 months "
            "of real-time data (real-time study ongoing). In-use stability after "
            "pouch opening: 1 hour."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = AssayPerformanceClaimWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running AssayPerformanceClaimWorkflow...")
    print(f"Assay: {request.assay_description[:80]}...")
    print(f"Claim set: {request.claim_set[:80]}...")
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
    print("ASSAY CHECKLIST:")
    for item in result.metadata["assay_checklist"]:
        print(f"  {item}")
    print()

    sen = result.metadata["sensitivity_claim_flags"]
    spe = result.metadata["specificity_claim_flags"]
    itf = result.metadata["interference_flags"]
    if sen or spe or itf:
        print(f"Sensitivity-claim flags ({len(sen)}): {sen}")
        print(f"Specificity-claim flags ({len(spe)}): {spe}")
        print(f"Interference flags ({len(itf)}): {itf}")


if __name__ == "__main__":
    asyncio.run(main())
