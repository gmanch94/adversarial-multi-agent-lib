"""
Example — ClinicalTrialEligibilityWorkflow

Synthetic scenario: 68-year-old Black woman with HFrEF (LVEF 32%) and CKD
Stage 2 (eGFR 48 mL/min/1.73m²) being assessed for a Phase III cardiology
RCT of a novel SGLT2 inhibitor.

This scenario exercises two distinct veto triggers:
  1. Clinical eligibility check — safety exclusion verification against
     protocol section numbers (ICH-GCP gate).
  2. Bias detection — under-representation of Black women in cardiology RCTs
     (JAMA 2019 pattern; Duma et al., JAMA Cardiol. 2019;4(3):211-219).
     Protocol §4.2 explicitly permits all demographics; any reasoning that
     uses race or sex as a determinative exclusion factor without protocol-
     specified clinical justification triggers a reviewer veto.

Expected outcome (clean run): ELIGIBLE per §3.1 / §4.1; no BIAS FLAGS;
no safety exclusions triggered; REVIEWER VETO: None.

To exercise the bias-veto path: modify patient_profile or site_context to
include reasoning that excludes on protected-class grounds without protocol
justification — the reviewer will veto.

⚠️  NOT FOR PRODUCTION USE. Synthetic data only. See PRODUCTION_GAPS in the
    workflow module.

Usage:
    export ANTHROPIC_API_KEY=...
    export OPENAI_API_KEY=...   # or set reviewer_provider=ANTHROPIC in Config
    python examples/healthcare/clinical_trial_eligibility.py
"""
from __future__ import annotations

import asyncio
import json
import os

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
    ClinicalTrialEligibilityWorkflow,
    TrialEligibilityRequest,
)


def build_agents(config: Config) -> tuple[object, object]:
    from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    return executor, reviewer


async def main() -> None:
    workspace = os.environ.get(
        "WORKSPACE_DIR", "/tmp/clinical_trial_eligibility_example"
    )
    os.makedirs(workspace, exist_ok=True)

    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        reviewer_provider=ReviewerProvider.OPENAI,
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        workspace_dir=workspace,
        max_review_rounds=3,
        score_threshold=8.0,
    )

    executor, reviewer = build_agents(config)

    request = TrialEligibilityRequest(
        trial_id="NCT-CARDIO-2026-001",
        protocol_summary=(
            "Phase III RCT: Novel SGLT2 inhibitor (empagliflozin-X 25mg daily) "
            "vs placebo in HFrEF. Sponsor: CardioInnovate Inc. "
            "Inclusion §3.1: NYHA Class II-IV heart failure; LVEF < 40% on "
            "echocardiography within 6 months; age 18-80; eGFR >= 20 mL/min/1.73m². "
            "Inclusion §3.2: Stable background therapy (ACE inhibitor, ARB, or ARNi + "
            "beta-blocker) for >= 3 months. "
            "Exclusion §4.1: eGFR < 20 mL/min/1.73m²; active systemic infection "
            "requiring IV antibiotics; concomitant SGLT2 inhibitor use at screening; "
            "severe hepatic impairment (Child-Pugh C). "
            "Exclusion §4.2: No sex, race, ethnicity, or disability exclusions — "
            "all demographics are eligible. Under-represented groups are encouraged "
            "to enroll per NIH diversity policy. "
            "Washout §5.1: Prior SGLT2 inhibitor requires 4-week washout before screening."
        ),
        patient_profile=(
            "68-year-old Black woman. NYHA Class III heart failure with reduced "
            "ejection fraction (HFrEF). Type 2 diabetes mellitus (HbA1c 7.8%). "
            "eGFR 48 mL/min/1.73m² (CKD Stage 2, stable x 12 months). "
            "Hypertension (BP 134/82 on treatment). Non-smoker. BMI 29. "
            "No active systemic infection. No documented hepatic impairment. "
            "Patient was referred by primary cardiologist; expressed interest in "
            "participation after reading the patient information sheet."
        ),
        biomarker_status=(
            "Echocardiography (2026-04-28): LVEF 32% (Simpson biplane). "
            "BNP: 720 pg/mL. eGFR: 48 mL/min/1.73m² (CKD-EPI, 2026-05-02). "
            "Creatinine: 1.2 mg/dL. HbA1c: 7.8% (2026-04-15). "
            "ALT: 24 U/L. AST: 21 U/L (hepatic function within normal limits). "
            "Na: 137 mEq/L. K: 4.3 mEq/L. No troponin elevation."
        ),
        prior_treatments=(
            "Sacubitril/valsartan 97/103mg BID (on board 14 months — meets §3.2 "
            "stable ARNi background therapy criterion). "
            "Metoprolol succinate 50mg daily (on board 14 months — meets §3.2 "
            "stable beta-blocker criterion). "
            "Furosemide 40mg daily for volume management. "
            "Metformin 500mg BID for type 2 diabetes. "
            "No prior SGLT2 inhibitor use — §5.1 washout not required. "
            "Aspirin 81mg daily. Atorvastatin 40mg nightly."
        ),
        competing_risks=(
            "CKD Stage 2 (eGFR 48): above §4.1 exclusion threshold of eGFR < 20. "
            "Type 2 diabetes: SGLT2 inhibitor has documented glycaemic benefit — "
            "noted as a secondary endpoint in the protocol; not an exclusion. "
            "Sacubitril/valsartan: protocol §4.1 does not list ARNi as a prohibited "
            "concomitant medication; sacubitril/valsartan meets §3.2 stable background "
            "therapy criterion. "
            "No active infection, no severe hepatic impairment, no concomitant SGLT2 "
            "inhibitor — all §4.1 safety exclusions are clear."
        ),
        site_context=(
            "Enrolling site: University Medical Center, urban catchment area. "
            "Current enrolled cohort (n=47): 76% male, 81% non-Hispanic white, "
            "11% Black or African American, 6% Hispanic/Latino, 2% Asian. "
            "Site enrollment log notes under-representation of Black women relative "
            "to HFrEF disease prevalence in the catchment area (estimated 18% of "
            "HFrEF patients in the area are Black women per regional registry data). "
            "Site has implemented targeted outreach per NIH diversity enrollment policy. "
            "IRB coordinator has been briefed on JAMA 2019 cardiology RCT "
            "under-representation literature (Duma et al.)."
        ),
    )

    wf = ClinicalTrialEligibilityWorkflow(
        executor=executor,  # type: ignore[arg-type]
        reviewer=reviewer,  # type: ignore[arg-type]
        config=config,
        ledger=ClaimLedger(str(workspace + "/ledger.json")),
        wiki=ResearchWiki(str(workspace + "/wiki.json")),
    )

    print("Running ClinicalTrialEligibilityWorkflow...")
    print("Trial:   NCT-CARDIO-2026-001 (Phase III SGLT2 inhibitor in HFrEF)")
    print("Patient: 68yo Black woman, NYHA III HFrEF (LVEF 32%), CKD2 (eGFR 48)")
    print("Bias-gate: reviewer checks JAMA 2019 cardiology RCT pattern")
    print("=" * 70)

    result = await wf.run(request=request)

    print(f"\nConverged:   {result.converged}")
    print(f"Rounds:      {result.rounds}")
    print(f"Final score: {result.final_score:.1f}/10")

    vetoed = result.metadata.get("vetoed", False)
    print(f"Vetoed:      {vetoed}")
    if vetoed:
        print(f"\nVETO REASON:\n{result.metadata['veto_reason']}")

    print(f"\nBIAS FLAGS ({len(result.metadata['bias_flags'])}):")
    for flag in result.metadata["bias_flags"]:
        print(f"  - {flag}")

    print(f"\nELIGIBILITY FLAGS ({len(result.metadata['eligibility_flags'])}):")
    for flag in result.metadata["eligibility_flags"]:
        print(f"  - {flag}")

    print(f"\nEVIDENCE FLAGS ({len(result.metadata['evidence_flags'])}):")
    for flag in result.metadata["evidence_flags"]:
        print(f"  - {flag}")

    print("\nCHECKLIST:")
    for item in result.metadata["trial_checklist"]:
        print(f"  {item}")

    print(f"\nDISCLAIMER:\n{result.metadata['disclaimer']}")

    print("\n" + "=" * 70)
    print("FULL OUTPUT:")
    print(result.output)

    ledger_summary = result.metadata["ledger_summary"]
    print(f"\nLedger: {json.dumps(ledger_summary, indent=2)}")


if __name__ == "__main__":
    asyncio.run(main())
