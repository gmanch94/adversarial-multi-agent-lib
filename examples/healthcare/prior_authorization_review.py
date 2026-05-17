"""Example — PriorAuthorizationReviewWorkflow with synthetic specialty drug PA scenario.

Run: python -m examples.healthcare.prior_authorization_review

Requires: ANTHROPIC_API_KEY (executor) + OPENAI_API_KEY (reviewer) or
SAME-FAMILY pairing (REVIEWER_PROVIDER=anthropic).

Scenario: 65yo male with confirmed wild-type ATTR-CM requesting tafamidis
(Vyndaqel) 61 mg — specialty drug, high cost, FDA-approved for indication,
InterQual criteria met, step therapy documented.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.healthcare.workflows.prior_authorization_review import (
    PriorAuthRequest,
    PriorAuthorizationReviewWorkflow,
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
    workflow = PriorAuthorizationReviewWorkflow(
        executor=executor, reviewer=reviewer, config=config
    )

    request = PriorAuthRequest(
        member_id="MEM-2026-004881",
        requested_service=(
            "Tafamidis meglumine (Vyndaqel) 61 mg oral daily — "
            "90-day supply via specialty pharmacy. "
            "AWP ~$225,000/year."
        ),
        clinical_rationale=(
            "65yo male with biopsy-confirmed wild-type transthyretin amyloid "
            "cardiomyopathy (ATTR-CM). Technetium-99m pyrophosphate (Tc-PYP) "
            "scintigraphy grade 3 uptake (H/CL ratio 1.9). Cardiac MRI: "
            "LVEF 45%, diffuse late gadolinium enhancement consistent with "
            "amyloid infiltration. NYHA class II–III heart failure on optimized "
            "GDMT for 18 months. Cardiologist (Dr. A. Mehta, MD) attests medical "
            "necessity and has completed the prescriber attestation form."
        ),
        diagnosis_codes=(
            "I43 (Cardiomyopathy in diseases classified elsewhere), "
            "E85.4 (Organ-limited amyloidosis), "
            "I50.32 (Chronic diastolic heart failure, unspecified)"
        ),
        clinical_guidelines=(
            "ACC/AHA/HFSA Heart Failure Guideline 2022 Section 7.5: tafamidis "
            "recommended (Class I, LOE B-R) for patients with ATTR-CM and NYHA "
            "class I–III symptoms to reduce cardiovascular mortality and "
            "hospitalization. "
            "InterQual 2025 Specialty Drug PA Criteria — Tafamidis: requires "
            "(1) confirmed ATTR-CM via Tc-PYP scintigraphy grade 2–3 or tissue "
            "biopsy, (2) NYHA class I–III, (3) LVEF documented, "
            "(4) prescriber attestation. "
            "Acme PPO Formulary Tier 5 Specialty: requires PA; not subject to "
            "step therapy (no disease-modifying alternatives exist for ATTR-CM)."
        ),
        member_history=(
            "65yo male, Acme PPO commercial plan. No prior tafamidis claims. "
            "Active prescriptions: furosemide 40 mg daily, carvedilol 12.5 mg "
            "BID, spironolactone 25 mg daily (stable GDMT x 18 months). "
            "Comorbidities: CKD stage 2 (eGFR 62 mL/min), HTN. "
            "Genetic testing: negative for hereditary TTR variants "
            "(Val122Ile, Val30Met) — confirms wild-type ATTR-CM. "
            "No CHF hospitalizations in past 12 months."
        ),
        alternatives_tried=(
            "Patient completed 18 months of optimized guideline-directed medical "
            "therapy (GDMT): lisinopril 10 mg titrated to carvedilol 12.5 mg BID "
            "+ spironolactone 25 mg daily. Persistent NYHA class II–III symptoms "
            "despite optimization. "
            "Diflunisal considered but contraindicated: CKD stage 2 (eGFR 62) "
            "exceeds safe NSAID threshold per nephrology consult 2026-03-15. "
            "No disease-modifying alternative approved for ATTR-CM (FDA as of "
            "2026-01-01); step therapy not applicable per Acme PPO formulary "
            "exception criteria Section 4.2."
        ),
    )

    result = await workflow.run(request=request)

    print(f"\n{'='*60}")
    print(f"Converged: {result.converged} in {result.rounds} rounds")
    print(f"Final score: {result.final_score}/10")
    print(f"{'='*60}\n")
    print(result.output)
    print(f"\n{'='*60}")
    print(f"Medical-necessity flags: {result.metadata['medical_necessity_flags']}")
    print(f"Coverage flags:          {result.metadata['coverage_flags']}")
    print(f"Documentation flags:     {result.metadata['documentation_flags']}")
    print("\nChecklist:")
    for item in result.metadata["prior_auth_checklist"]:
        print(f"  {item}")


if __name__ == "__main__":
    asyncio.run(main())
