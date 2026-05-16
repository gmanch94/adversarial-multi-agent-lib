"""Durable wrapper around ClinicalTrialEligibilityWorkflow with 3 named pause gates.

Pause gates per design spec section "Concrete deliverable":
1. post-criteria-eval    pause if labs incomplete (rolling-data trigger)
2. post-bias-check       pause if bias-gate flags require IRB sign-off (approver-SLA trigger)
3. post-evidence-review  pause for FDA 21 CFR 312 window if AE signal (regulatory-clock trigger)

The original ClinicalTrialEligibilityWorkflow is NOT modified; this subclass
adds run_round() while preserving the inherited run() (used in non-durable mode).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from ...core.durable.workflow import PauseContext
from .clinical_trial_eligibility import (
    ClinicalTrialEligibilityWorkflow,
    TrialEligibilityRequest,
)


class ClinicalTrialEligibilityDurableWorkflow(ClinicalTrialEligibilityWorkflow):
    """Durable-aware subclass exposing run_round() for DurableWorkflow.

    POC scope: pause conditions are static heuristics on the parent's existing
    flag lists. Production callers override _should_pause_after_round to bind
    pause decisions to real labs-ready / IRB-sign-off / regulatory-clock backends.
    """

    async def run_round(
        self,
        round_num: int,
        request: TrialEligibilityRequest,
        prior_state: dict[str, Any] | None,
        ctx: PauseContext | None = None,
    ) -> dict[str, Any]:
        original_max = self.config.max_review_rounds
        try:
            self.config.max_review_rounds = 1
            wf_result = await super().run(request=request)
        finally:
            self.config.max_review_rounds = original_max

        if ctx is not None and round_num == 1:
            protocol_text = getattr(request, "protocol_summary", "") or ""
            biomarker_text = getattr(request, "biomarker_status", "") or ""
            combined = f"{protocol_text} {biomarker_text}".lower()
            if "labs pending" in combined:
                await ctx.pause(
                    reason="rolling_data",
                    context={"awaiting": "labs", "round": round_num},
                    wake_at=None,
                )
            bias_flags = wf_result.metadata.get("bias_flags", [])
            if bias_flags:
                await ctx.pause(
                    reason="approver_sla",
                    context={"awaiting": "irb_signoff", "flags": list(bias_flags)},
                    wake_at=None,
                )
            evidence_flags = wf_result.metadata.get("evidence_flags", [])
            if any("adverse event" in str(f).lower() for f in evidence_flags):
                wake = (datetime.now(timezone.utc) + timedelta(days=7)).isoformat()
                await ctx.pause(
                    reason="regulatory_clock",
                    context={"clock": "FDA_21_CFR_312_7d", "flags": list(evidence_flags)},
                    wake_at=wake,
                )

        return {
            "output": wf_result.output,
            "score": wf_result.final_score,
            "converged": wf_result.converged,
            "rounds_history_entry": {
                "round": round_num,
                "score": wf_result.final_score,
                "converged": wf_result.converged,
                "bias_flags": wf_result.metadata.get("bias_flags", []),
                "eligibility_flags": wf_result.metadata.get("eligibility_flags", []),
                "evidence_flags": wf_result.metadata.get("evidence_flags", []),
            },
            "metadata": wf_result.metadata,
            "next_state": {"last_score": wf_result.final_score},
        }
