"""Durable clinical-trial eligibility workflow  start, pause, resume lifecycle.

Synthetic de-identified data (not PHI). Demonstrates:
- start() with a request that triggers the rolling_data pause gate
- resume() with MergeFreshInputsHook providing fresh labs
- Final convergence after labs are complete

Run: python -m examples.healthcare.clinical_trial_durable
"""
from __future__ import annotations

import asyncio
import os
from pathlib import Path

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.durable.checkpoint import FileCheckpointStore
from adv_multi_agent.core.durable.hooks import MergeFreshInputsHook
from adv_multi_agent.core.durable.lock import FileRunLock
from adv_multi_agent.core.durable.workflow import DurableWorkflow
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
    TrialEligibilityRequest,
)
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
    ClinicalTrialEligibilityDurableWorkflow,
)


def _build_request(labs_text: str) -> TrialEligibilityRequest:
    return TrialEligibilityRequest(
        trial_id="NCT-SYNTH-2026-001",
        protocol_summary=(
            "Synthetic Protocol SYN-LUNG-2026-001. Phase II EGFR inhibitor plus "
            f"checkpoint inhibitor in NSCLC. Inclusion 3.1: ECOG 0-1. Note: {labs_text}"
        ),
        patient_profile=(
            "Synthetic ID PAT-SYNTH-2026-A. 62yo, primary language English. "
            "PRIMARY: NSCLC (cT3N2M0). PMH: HTN, T2DM. ECOG 1."
        ),
        biomarker_status="EGFR L858R positive (NGS, reported 2026-05-10)",
        prior_treatments="None  newly diagnosed; no washout required",
        competing_risks="No significant organ dysfunction; CrCl 78",
        site_context="50 percent female, 30 percent non-white enrolled at this site",
    )


async def main() -> None:
    workspace = Path(os.environ.get("DURABLE_WORKSPACE", "./.durable_workspace"))
    workspace.mkdir(parents=True, exist_ok=True)

    config = Config(
        workspace_dir=str(workspace),
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=8.0,
    )
    inner = ClinicalTrialEligibilityDurableWorkflow(config=config)
    store = FileCheckpointStore(base_dir=workspace / "checkpoints")
    lock = FileRunLock(base_dir=workspace / "locks")
    dw = DurableWorkflow(
        inner=inner,
        config=config,
        checkpoint_store=store,
        run_lock=lock,
        reconciliation_hook=MergeFreshInputsHook(request_type=TrialEligibilityRequest),
    )

    print("=== Round 1: start (expect pause on rolling_data  labs pending) ===")
    outcome = await dw.start(_build_request("labs pending  CBC + CMP not yet drawn."))
    print(f"status={outcome.status}, pause_reason={outcome.pause_reason}")
    print(f"run_id={outcome.token.run_id}, wake_at={outcome.token.wake_at}")
    if outcome.status != "paused":
        print(f"unexpected: {outcome}")
        return

    print("\n=== Simulating 14 days of waiting  labs now back ===")
    print("=== Resume with fresh labs ===")
    resumed = await dw.resume(
        outcome.token,
        fresh_inputs=_build_request("labs complete: CBC WBC 6.2, Hgb 13.1, Plt 220k."),
    )
    print(f"status={resumed.status}")
    if resumed.result is not None:
        print(f"final_score={resumed.result.final_score}")
        print(f"converged={resumed.result.converged}")
        print(f"rounds={resumed.result.rounds}")


if __name__ == "__main__":
    asyncio.run(main())
