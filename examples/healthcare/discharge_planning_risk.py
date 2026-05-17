"""Example — DischargePlanningRiskWorkflow with synthetic CHF readmission scenario.

Run: python -m examples.healthcare.discharge_planning_risk

Requires: ANTHROPIC_API_KEY (executor) + OPENAI_API_KEY (reviewer) or
SAME-FAMILY pairing (REVIEWER_PROVIDER=anthropic).

Scenario: 78yo woman, CHF exacerbation, prior 30-day readmission, lives alone,
food-security concern, no transportation for follow-up.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.healthcare.workflows.discharge_planning_risk import (
    DischargePlanningRequest,
    DischargePlanningRiskWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=__import__("os").environ.get("ANTHROPIC_API_KEY", ""),
        openai_api_key=__import__("os").environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir=str(Path.cwd() / ".healthcare_workspace"),
        max_review_rounds=4,
        score_threshold=7.5,
    )
    executor = ExecutorAgent(config)
    reviewer = ReviewerAgent(config)
    workflow = DischargePlanningRiskWorkflow(
        executor=executor, reviewer=reviewer, config=config
    )

    request = DischargePlanningRequest(
        patient_summary=(
            "78yo female with CHF (EF 30%), HTN, DM2, and CKD stage 3. "
            "Lives alone in a second-floor apartment with no elevator. "
            "No family in the area. Primary language English."
        ),
        hospitalization_summary=(
            "Admitted for acute CHF exacerbation with 8 kg volume overload. "
            "Diuresed with IV furosemide 80 mg BID; euvolemic by day 4. "
            "BNP trended from 4,200 to 980 pg/mL. LOS 5 days. "
            "No arrhythmia; echo unchanged from prior (EF 30%)."
        ),
        proposed_discharge_plan=(
            "Discharge to home with home health nursing 3 times per week for "
            "medication management and daily weight monitoring. Resume home "
            "medications with furosemide dose increased from 40 mg to 60 mg "
            "daily. Follow-up with cardiologist in 7 days."
        ),
        social_determinants=(
            "Patient relies on community meals program (Meals on Wheels) for "
            "nutrition — enrolled but delivery not confirmed post-discharge. "
            "No personal vehicle; cannot take public transit due to mobility "
            "limitations. Medicare + Medicaid dual-eligible. "
            "Food-security concern: fixed income, limited grocery access."
        ),
        readmission_history=(
            "Two CHF-related admissions in the past 12 months. "
            "Prior discharge 34 days ago followed by readmission within 30 days "
            "for volume overload (medication non-adherence identified). "
            "LACE score 14 (high risk: L=3, A=4, C=4, E=3)."
        ),
        care_team_notes=(
            "PT/OT: functional baseline restored; safe for home environment "
            "with current mobility aids. "
            "SW: transportation barrier documented; medical transport referral "
            "placed but not yet confirmed. Meals on Wheels delivery re-enrolled. "
            "Nursing: patient and daughter (by phone) educated on daily weights, "
            "sodium restriction, and when to call for worsening symptoms. "
            "Pharmacy: medication reconciliation completed; no duplications."
        ),
    )

    result = await workflow.run(request=request)

    print(f"\n{'='*60}")
    print(f"Converged: {result.converged} in {result.rounds} rounds")
    print(f"Final score: {result.final_score}/10")
    print(f"{'='*60}\n")
    print(result.output)
    print(f"\n{'='*60}")
    print(f"Readmission flags: {result.metadata['readmission_flags']}")
    print(f"Care-gap flags:    {result.metadata['care_gap_flags']}")
    print(f"SDOH flags:        {result.metadata['social_determinant_flags']}")
    print("\nChecklist:")
    for item in result.metadata["discharge_checklist"]:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
