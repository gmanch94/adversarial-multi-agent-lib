"""Example — ClaimsAppealReviewWorkflow with synthetic cardiac MRI denial appeal.

Run: python -m examples.healthcare.claims_appeal_review

Requires: ANTHROPIC_API_KEY (executor) + OPENAI_API_KEY (reviewer) or
SAME-FAMILY pairing (REVIEWER_PROVIDER=anthropic).

Scenario: 58yo female with suspected cardiac sarcoidosis. Cardiac MRI with
contrast (CPT 75561) denied as not medically necessary — reviewer applied
InterQual 2025 cardiology criteria and deemed echo sufficient. Member appeals:
echo non-diagnostic for infiltrative cardiomyopathy; ACC/AHA 2023 guideline
section 4.3 explicitly indicates MRI when echo is non-diagnostic; coverage
policy IMG-007 effective 2026-01-01 covers the service.
"""
from __future__ import annotations

import asyncio
from pathlib import Path

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.healthcare.workflows.claims_appeal_review import (
    ClaimsAppealRequest,
    ClaimsAppealReviewWorkflow,
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
    workflow = ClaimsAppealReviewWorkflow(
        executor=executor, reviewer=reviewer, config=config
    )

    request = ClaimsAppealRequest(
        claim_id="CLM-2026-004512",
        denied_service="Cardiac MRI with contrast (CPT 75561)",
        appeal_narrative=(
            "Member appeals denial of cardiac MRI ordered by cardiologist "
            "Dr. Rivera on 2026-04-10. Echocardiogram dated 2026-03-15 was "
            "non-diagnostic for suspected cardiac sarcoidosis — biventricular "
            "dysfunction and NSVT on Holter without infiltrative pattern "
            "confirmation. ACC/AHA 2023 guideline section 4.3 explicitly "
            "indicates cardiac MRI when echo is non-diagnostic for suspected "
            "infiltrative cardiomyopathy. Denial applied InterQual 2025 criteria "
            "but did not account for guideline indication or policy IMG-007 "
            "effective 2026-01-01 which covers this service when documentation "
            "requirements are met."
        ),
        clinical_evidence=(
            "Echocardiogram 2026-03-15: biventricular dysfunction EF 40%, "
            "diffuse wall motion abnormality, non-diagnostic for infiltrative "
            "cardiomyopathy. "
            "Holter monitor 2026-03-22: multiple runs of NSVT (up to 8 beats). "
            "PET scan 2026-02-28: increased FDG uptake right ventricle, "
            "non-specific but concerning for sarcoidosis. "
            "ACC/AHA 2023 Heart Failure Guideline section 4.3: 'Cardiac MRI "
            "with gadolinium is recommended for patients with suspected "
            "infiltrative cardiomyopathy when echocardiography is non-diagnostic "
            "(Class I, LOE B-NR).'"
        ),
        coverage_policy=(
            "Acme Health Plan Imaging Policy IMG-007 effective 2026-01-01: "
            "Cardiac MRI with contrast (CPT 75561) is covered when: "
            "(1) ordering cardiologist documents clinical indication; "
            "(2) echocardiogram is non-diagnostic for the suspected condition; "
            "(3) clinical indication is consistent with ACC/AHA or SCMR guideline. "
            "Prior authorization required for outpatient setting."
        ),
        original_review_summary=(
            "Claim denied 2026-04-18 by Dr. Chen (Medical Reviewer). "
            "Reason: cardiac MRI not medically necessary; InterQual 2025 "
            "Cardiology criteria applied; echocardiogram deemed sufficient "
            "for cardiac evaluation. "
            "No reference to ACC/AHA guideline 4.3 or coverage policy IMG-007 "
            "in denial letter. "
            "First-level appeal rights: 30 days from denial date (2026-05-18). "
            "Appeal received 2026-05-02 — within timeline."
        ),
        treating_physician_statement=(
            "Dr. Rivera, MD (Cardiology, Board Certified): "
            "Echocardiogram is non-diagnostic for cardiac sarcoidosis in this "
            "patient. Cardiac MRI with gadolinium is the gold-standard test per "
            "ACC/AHA 2023 Class I recommendation and is essential for diagnosis "
            "and treatment planning. Without MRI, we cannot confirm or exclude "
            "sarcoidosis, cannot assess late gadolinium enhancement pattern for "
            "arrhythmia risk stratification, and cannot guide immunosuppressive "
            "therapy. Denial based solely on InterQual criteria without "
            "considering guideline indication is clinically inappropriate."
        ),
    )

    result = await workflow.run(request=request)

    print(f"\n{'='*60}")
    print(f"Converged: {result.converged} in {result.rounds} rounds")
    print(f"Final score: {result.final_score}/10")
    print(f"{'='*60}\n")
    print(result.output)
    print(f"\n{'='*60}")
    print(f"Evidence flags:  {result.metadata['evidence_flags']}")
    print(f"Coverage flags:  {result.metadata['coverage_flags']}")
    print(f"Procedure flags: {result.metadata['procedure_flags']}")
    print("\nAppeal checklist:")
    for item in result.metadata["appeal_checklist"]:
        print(f"  {item}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())
