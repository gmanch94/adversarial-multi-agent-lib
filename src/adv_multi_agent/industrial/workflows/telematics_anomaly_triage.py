"""
Workflow — Telematics Anomaly Triage (Industrial IoT Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to industrial-
IoT telematics anomaly triage — taking a raw signal-payload alert (shock
event, battery anomaly, utilization deviation) from a fleet-telematics
platform (Crown InfoLink, Hyster Tracker, Linde connect:) and producing
an actionable maintenance / service / safety brief.

Executor drafts an anomaly-triage brief; reviewer (recommended: different
model family per ARIS §2.1 principle 1) challenges weak-signal alerts
that would waste a truck-roll, optimistic actionability claims (when the
signal isn't strong enough to act), and missing false-positive analysis.

Triple-flag gate (D-IND-1): SIGNAL-EVIDENCE FLAGS, FALSE-POSITIVE-COST
FLAGS, ACTIONABILITY FLAGS. **No reviewer veto** — telematics triage is
operational; veto class belongs in product-liability / recall workflows.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Telematics platform integration — InfoLink / Hyster Tracker / Linde
       connect: structured signal streams, not paraphrased prose.
    2. Anomaly-detection model — production signal-vs-noise discrimination
       belongs in a tuned per-equipment-class detector with calibrated
       false-positive rate, not LLM heuristic.
    3. CMMS dispatch integration — recommended actions must integrate with
       the work-order system; service-network capacity must be checked.
    4. Equipment digital-twin — utilization, duty-cycle, and component
       wear-baseline data must come from a structured digital-twin
       representation per asset.
    5. Parts availability — recommended parts replacements must verify
       against parts catalog + DC inventory + service-network reach.
    6. Customer-contract context — SLA terms, on-site spare equipment, and
       service-level commitments belong in a structured CRM, not narrative.
    7. Append-only audit store + dedicated third-model auditor — see
       ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import (
    extract_flags,
    sanitize_for_prompt,
    truncate_flag_display,
)
from ...core.workflow import BaseWorkflow, WorkflowResult

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated telematics-anomaly triage is "
    "not an authorised maintenance dispatch or customer notification. A "
    "credentialed service-engineering reviewer must verify the signal "
    "strength, false-positive analysis, and proposed action against the "
    "calibrated detector output and digital-twin baseline before any "
    "truck-roll or customer notification is issued. AI output must "
    "never trigger an automated dispatch."
)

_TELEMATICS_REVIEW_CRITERIA = """\
Evaluate this telematics-anomaly triage on four dimensions. Score each 0–10.

1. SIGNAL EVIDENCE (35%) — CRITICAL
   Is the anomaly signal characterised quantitatively (magnitude, duration,
   deviation-from-baseline, equipment-class detector threshold)? Are
   corroborating signals (multiple sensors, repeat occurrence, environmental
   context) cited? Penalise single-reading alerts framed as actionable.
   Flag every gap under SIGNAL-EVIDENCE FLAGS:.

2. FALSE-POSITIVE-COST DISCIPLINE (30%) — CRITICAL
   Is the false-positive base rate for this signal class stated? Is the
   cost of a wasted truck-roll / unnecessary parts swap / customer-trust
   hit balanced against the cost of inaction? Penalise actionability
   claims that ignore detector precision. Flag every gap under
   FALSE-POSITIVE-COST FLAGS:.

3. ACTIONABILITY (25%) — CRITICAL
   Are the recommended actions specific (dispatch / customer-notify /
   continue-monitoring / escalate-to-engineering) with the trigger
   threshold for each? Are parts availability and service-network
   capacity verified? Penalise vague "investigate further" outputs that
   create operational noise. Flag every gap under ACTIONABILITY FLAGS:.

4. CONTEXT INTEGRATION (10%)
   Are utilization, duty-cycle, customer-contract-SLA, equipment-age, and
   recent-service-history considered? Is the digital-twin baseline cited?

Overall score = weighted average.
Score ≥ 7.5 AND zero SIGNAL-EVIDENCE FLAGS AND zero FALSE-POSITIVE-COST
FLAGS AND zero ACTIONABILITY FLAGS: triage is ready for service-
engineering review. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SIGNAL-EVIDENCE FLAGS: [bullet list, or "None detected"]
  FALSE-POSITIVE-COST FLAGS: [bullet list, or "None detected"]
  ACTIONABILITY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a telematics-anomaly triage for an industrial OEM's
service-engineering team. You have no stake in the outcome. Your job is
to triage the signal into a specific next action with the false-positive
cost weighed against the cost of inaction — not to dispatch on every
alert, not to dismiss the signal for operational convenience.

BASE THE TRIAGE ON THE INPUT DATA.

ANOMALY DATA:
{request_text}

{wiki_context}

Produce a structured triage with exactly these sections:

## Signal Summary
Restate the anomaly: asset serial, signal class (shock / battery / drive /
utilization / safety-system), magnitude, duration, deviation-from-baseline,
detector confidence.

## Equipment and Customer Context
Equipment class, age, duty-cycle pattern, customer-contract SLA, on-site
spare-equipment posture, recent-service history.

## Failure-Mode Hypothesis
Candidate failure modes consistent with the signal class. Rank by signal-
mode fit, deployed-population priors, and recent-service correlation.

## False-Positive Analysis
False-positive base rate for this signal class. Cost of wasted truck-roll
+ parts swap + customer-trust hit. Cost of inaction (downtime, escalation,
safety risk).

## Recommended Action
Dispatch / customer-notify / continue-monitoring / escalate-to-engineering.
State the parts (verified against catalog + DC + service-network reach),
the priority tier, and the customer communication.

## Threshold for Escalation
What additional signal would upgrade to dispatch / escalate-to-engineering?
What signal would close as resolved?

## Evidence Gaps
Information missing from the inputs that materially affects triage.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this telematics-anomaly triage. Address EVERY issue in the
reviewer's critique, especially any SIGNAL-EVIDENCE FLAGS,
FALSE-POSITIVE-COST FLAGS, or ACTIONABILITY FLAGS.

PREVIOUS TRIAGE:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SIGNAL-EVIDENCE FLAG: quantify the anomaly (magnitude /
duration / deviation-from-baseline / corroborating signals) or downgrade
the actionability.
⚠️  For any FALSE-POSITIVE-COST FLAG: state the false-positive base rate
and the cost-of-truck-roll vs cost-of-inaction balance.
⚠️  For any ACTIONABILITY FLAG: replace vague language with a specific
action + parts + priority tier + escalation threshold.
"""


@dataclass
class TelematicsAnomalyTriageRequest:
    """Structured input for the telematics-anomaly-triage workflow."""

    asset_summary: str
    """Asset serial, equipment class, age, customer."""

    signal_payload: str
    """Anomaly signal: class, magnitude, duration, deviation-from-baseline,
    detector confidence, corroborating signals."""

    duty_cycle_baseline: str
    """Asset's recent utilization, duty-cycle pattern, digital-twin baseline."""

    recent_service_history: str
    """Recent service / parts / firmware activity on this asset."""

    customer_contract_context: str
    """Customer SLA terms, on-site spare equipment, prior incident posture."""

    parts_and_service_network: str
    """Parts availability + DC + service-network reach for the candidate
    failure modes."""

    initial_recommendation: str
    """Service-engineer first-pass action + reasoning."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Asset summary: {self.asset_summary[:cap]}",
            f"Signal payload: {self.signal_payload[:cap]}",
            f"Duty-cycle baseline: {self.duty_cycle_baseline[:cap]}",
            f"Recent service history: {self.recent_service_history[:cap]}",
            f"Customer contract context: {self.customer_contract_context[:cap]}",
            f"Parts and service network: {self.parts_and_service_network[:cap]}",
            f"Initial recommendation: {self.initial_recommendation[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "SIGNAL-EVIDENCE FLAGS:",
    "FALSE-POSITIVE-COST FLAGS:",
    "ACTIONABILITY FLAGS:",
)


class TelematicsAnomalyTriageWorkflow(BaseWorkflow):
    """
    Adversarial telematics-anomaly triage: executor drafts a triage brief →
    reviewer challenges weak-signal alerts, missing false-positive
    discipline, and vague actionability → iterate.

    Convergence gate (D-IND-1):
        score ≥ threshold
        AND zero SIGNAL-EVIDENCE FLAGS
        AND zero FALSE-POSITIVE-COST FLAGS
        AND zero ACTIONABILITY FLAGS

    No reviewer veto — telematics triage is operational. Life-safety
    veto class is handled by ProductLiabilityRootCauseWorkflow / Recall.
    """

    async def run(  # type: ignore[override]
        self,
        request: TelematicsAnomalyTriageRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
        accumulated: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    request_text=request_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                prompt = _REVISION_PROMPT.format(
                    previous=sanitize_for_prompt(output, max_chars=10000),
                    score=f"{score:.1f}",
                    critique=sanitize_for_prompt(review.critique, max_chars=4000),
                    suggestions="\n".join(
                        f"- {sanitize_for_prompt(s, max_chars=500)}"
                        for s in review.suggestions
                    ),
                    flag_section=self._format_flag_section(current),
                    wiki_context=wiki_ctx,
                )

            output = await self.executor.run(prompt, context="")
            self._register_claims(output, round_num)

            review = await self.reviewer.review(
                output,
                criteria=_TELEMATICS_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=config.max_wiki_body_chars),
                round_num=round_num,
                score=score,
            )

            if review.approved and not any(current.values()):
                converged = True
                break

        approver_checklist = self._build_approver_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "asset_summary": request.asset_summary,
                "signal_evidence_flags": list(
                    dict.fromkeys(accumulated["SIGNAL-EVIDENCE FLAGS:"])
                ),
                "false_positive_cost_flags": list(
                    dict.fromkeys(accumulated["FALSE-POSITIVE-COST FLAGS:"])
                ),
                "actionability_flags": list(
                    dict.fromkeys(accumulated["ACTIONABILITY FLAGS:"])
                ),
                "approver_checklist": approver_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "SIGNAL-EVIDENCE FLAGS:": (
                "⚠️  SIGNAL-EVIDENCE FLAGS (quantify the anomaly or downgrade "
                "actionability):"
            ),
            "FALSE-POSITIVE-COST FLAGS:": (
                "⚠️  FALSE-POSITIVE-COST FLAGS (state base rate + cost of "
                "wasted truck-roll vs cost of inaction):"
            ),
            "ACTIONABILITY FLAGS:": (
                "⚠️  ACTIONABILITY FLAGS (replace vague language with "
                "specific action + parts + priority + escalation threshold):"
            ),
        }
        parts: list[str] = []
        for header in _FLAG_HEADERS:
            flags = current[header]
            if not flags:
                continue
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(flags)
            )
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _build_approver_checklist(
        request: TelematicsAnomalyTriageRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["SIGNAL-EVIDENCE FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  SIGNAL-EVIDENCE FLAGS "
                f"({len(accumulated['SIGNAL-EVIDENCE FLAGS:'])}) — "
                "verify detector output + digital-twin deviation before dispatch"
            )
        if accumulated["FALSE-POSITIVE-COST FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  FALSE-POSITIVE-COST FLAGS "
                f"({len(accumulated['FALSE-POSITIVE-COST FLAGS:'])}) — "
                "confirm base rate; service-engineering cost-benefit review"
            )
        if accumulated["ACTIONABILITY FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  ACTIONABILITY FLAGS "
                f"({len(accumulated['ACTIONABILITY FLAGS:'])}) — "
                "specify action + parts + priority + escalation threshold"
            )
        checklist.extend([
            "[ ] Service-engineering review before any customer-impacting action",
            "[ ] Verify parts availability against catalog + DC + service-network reach",
            "[ ] Confirm customer-contract SLA covers proposed action / response time",
            "[ ] Escalate to ProductLiabilityRootCauseWorkflow if safety-system signal",
            f"[ ] Confirm asset context: {request.asset_summary[:60]}",
            "[ ] Dispatch / customer-notify — AI output must not trigger automatic dispatch",
        ])
        return checklist
