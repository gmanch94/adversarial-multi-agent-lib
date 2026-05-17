"""
Example — TreatmentPlanReviewWorkflow

Synthetic scenario: 70-year-old male with CHF (EF 35%) and CKD Stage 3a
(eGFR 42 mL/min/1.73m²) — proposed contrast-enhanced coronary angiography
without documented pre-hydration prophylaxis.

Expected outcome: REVIEWER VETO on contrast-nephropathy procedure
contraindication (eGFR < 45 per ACR 2023 §4 requires prophylaxis;
plan omits it).

⚠️  NOT FOR PRODUCTION USE. Synthetic data only. See PRODUCTION_GAPS in the
    workflow module.

Usage:
    export ANTHROPIC_API_KEY=...
    export OPENAI_API_KEY=...   # or set reviewer_provider=ANTHROPIC in Config
    python examples/healthcare/treatment_plan_review.py
"""
from __future__ import annotations

import asyncio
import json
import os

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.healthcare.workflows.treatment_plan_review import (
    TreatmentPlanRequest,
    TreatmentPlanReviewWorkflow,
)


def build_agents(config: Config) -> tuple[object, object]:
    from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    return executor, reviewer


async def main() -> None:
    workspace = os.environ.get("WORKSPACE_DIR", "/tmp/treatment_plan_review_example")
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

    request = TreatmentPlanRequest(
        patient_summary=(
            "70-year-old male with NYHA Class III heart failure (EF 35%), "
            "CKD Stage 3a (eGFR 42 mL/min/1.73m²), type 2 diabetes mellitus "
            "(HbA1c 7.8%), hypertension (BP 148/90 on treatment). "
            "No documented drug allergies. Non-smoker. BMI 28."
        ),
        proposed_plan=(
            "1. Coronary angiography with iodinated contrast (60 mL Omnipaque-350) "
            "to evaluate suspected three-vessel coronary artery disease per "
            "recent nuclear stress test (reversible perfusion defect, anterior wall). "
            "2. Continue furosemide 40mg daily for volume management. "
            "3. Add lisinopril 5mg daily for RAAS blockade per ACC/AHA HF guideline. "
            "4. Refer to cardiac rehabilitation post-procedure."
        ),
        current_medications=(
            "Furosemide 40mg daily, metformin 1000mg BID, amlodipine 5mg daily, "
            "aspirin 81mg daily, atorvastatin 40mg nightly."
        ),
        lab_values=(
            "eGFR: 42 mL/min/1.73m² (CKD3a, stable x 6 months). "
            "Creatinine: 1.6 mg/dL. BUN: 28 mg/dL. "
            "BNP: 820 pg/mL. Na: 138 mEq/L. K: 4.1 mEq/L. "
            "ALT: 22 U/L. AST: 19 U/L. LDL: 88 mg/dL (on statin). "
            "HbA1c: 7.8%. Hgb: 11.9 g/dL."
        ),
        clinical_guidelines=(
            "ACC/AHA 2022 Heart Failure Guideline (doi:10.1161/CIR.0000000000001063); "
            "KDIGO 2012 Clinical Practice Guideline for CKD Evaluation and Management; "
            "ACR Manual on Contrast Media 2023 (Version 2023.1); "
            "ADA Standards of Care in Diabetes 2024."
        ),
        contraindication_context=(
            "CKD3a (eGFR 42 mL/min/1.73m²) — iodinated contrast carries "
            "contrast-induced nephropathy (CIN) risk. ACR 2023 Manual §4 (p.4): "
            "eGFR 30–44 requires pre-hydration (IV normal saline 1 mL/kg/h × 3–4h "
            "pre-procedure and 6h post-procedure) and consideration of N-acetylcysteine "
            "600mg BID the day before and day of procedure. "
            "Metformin must be held at time of contrast and for 48h post-procedure "
            "(lactic acidosis risk if contrast-induced AKI occurs). "
            "No documented allergy to contrast agents or penicillin. "
            "No prior contrast reaction. Furosemide should be held day of procedure "
            "to avoid additive volume depletion."
        ),
    )

    wf = TreatmentPlanReviewWorkflow(
        executor=executor,  # type: ignore[arg-type]
        reviewer=reviewer,  # type: ignore[arg-type]
        config=config,
        ledger=ClaimLedger(str(workspace + "/ledger.json")),
        wiki=ResearchWiki(str(workspace + "/wiki.json")),
    )

    print("Running TreatmentPlanReviewWorkflow...")
    print("Patient: 70yo CHF (EF 35%) + CKD3a (eGFR 42)")
    print("Proposed: contrast-enhanced coronary angiography (60 mL iodinated contrast)")
    print("Expected: VETO on contrast-nephropathy contraindication\n")

    result = await wf.run(request=request)

    print("=" * 70)
    print(f"Converged: {result.converged}")
    print(f"Rounds: {result.rounds}")
    print(f"Final score: {result.final_score:.1f}/10")
    print(f"Vetoed: {result.metadata.get('vetoed', False)}")
    print()

    if result.metadata.get("vetoed"):
        print("VETO REASON:")
        print(result.metadata["veto_reason"])
        print()

    print("GUIDELINE FLAGS:", result.metadata["guideline_flags"] or "None")
    print("CONTRAINDICATION FLAGS:", result.metadata["contraindication_flags"] or "None")
    print("RISK FLAGS:", result.metadata["risk_flags"] or "None")
    print()

    print("TREATMENT CHECKLIST:")
    for item in result.metadata["treatment_checklist"]:
        print(f"  {item}")
    print()

    print("OUTPUT (truncated to 1500 chars):")
    print(result.output[:1500])
    print()

    print("LEDGER SUMMARY:")
    print(json.dumps(result.metadata["ledger_summary"], indent=2))


if __name__ == "__main__":
    asyncio.run(main())
