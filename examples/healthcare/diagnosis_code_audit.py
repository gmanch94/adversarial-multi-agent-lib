"""Example — DiagnosisCodeAuditWorkflow with synthetic NSTEMI + PCI encounter.

Run: python -m examples.healthcare.diagnosis_code_audit
Requires: ANTHROPIC_API_KEY (executor) + OPENAI_API_KEY (reviewer) or
SAME-FAMILY pairing (REVIEWER_PROVIDER=anthropic).
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.healthcare.workflows.diagnosis_code_audit import (
    DiagnosisCodeAuditRequest,
    DiagnosisCodeAuditWorkflow,
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
    workflow = DiagnosisCodeAuditWorkflow(
        executor=executor, reviewer=reviewer, config=config
    )

    request = DiagnosisCodeAuditRequest(
        encounter_summary=(
            "65yo M admitted with NSTEMI. Cath shows 90% LAD lesion. "
            "PCI with DES placed. PMH: HTN, DM2 with stage-3 CKD. LOS 3 days. "
            "Discharged on dual antiplatelet therapy."
        ),
        proposed_codes=(
            "I21.4 (NSTEMI); E11.22 (DM2 w/CKD); I12.9 (HTN w/CKD unspecified); "
            "N18.30 (CKD3 unspecified); 92928 (PCI single vessel w/DES)"
        ),
        provider_specialty="cardiology",
        payer_guidelines=(
            "Medicare LCD L33797 (Cardiac Catheterization); "
            "AHA Coding Clinic Q2 2025 — HTN+CKD coding hierarchy."
        ),
        previous_audits=(
            "2025-Q1 audit found CKD stage specificity undercoded on 14% of "
            "cardiology encounters; corrective training delivered 2025-04-15."
        ),
        clinical_context="Inpatient admission; PCI procedure; 3-day LOS.",
    )

    result = await workflow.run(request=request)

    print(f"\n{'='*60}")
    print(f"Converged: {result.converged} in {result.rounds} rounds")
    print(f"Final score: {result.final_score}/10")
    print(f"{'='*60}\n")
    print(result.output)
    print(f"\n{'='*60}")
    print(f"Accuracy flags: {result.metadata['accuracy_flags']}")
    print(f"Compliance flags: {result.metadata['compliance_flags']}")
    print(f"Specificity flags: {result.metadata['specificity_flags']}")
    print(f"\nChecklist:")
    for item in result.metadata['audit_checklist']:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
