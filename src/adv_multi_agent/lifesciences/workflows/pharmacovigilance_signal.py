"""
Workflow — Pharmacovigilance Signal Evaluation (Lifesciences · Pharma, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to pharmacovigilance
signal management: executor evaluates an aggregate safety signal (strength,
population-level causality, labeling impact, proposed action); reviewer
(cross-model per ARIS §2.1) challenges any understated signal strength, dismissed
causality, and unreflected labeling impact, with the power to VETO when a signal
that meets the threshold for regulatory action is characterized as no-action.

BOUNDARY (D-LIFESCI-2): distinct from the healthcare AdverseEventTriageWorkflow —
that workflow grades clinical severity/causality for a single adverse event for a
provider; this evaluates an AGGREGATE safety signal (disproportionality across
cases) and its labeling / regulatory impact for the marketing-authorization
holder.

Veto gate (D-LIFESCI-4): fires when a signal meeting the threshold for regulatory
action / label change (e.g. a new serious identified risk) is characterized as
no-action / routine — an under-escalation that would breach the safety-signal
obligation.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Safety database — cases and their coding should resolve against the
       controlled safety database, not caller-pasted text.
    2. Signal-detection engine — disproportionality metrics should be produced
       by the controlled signal-detection engine (EVDAS / FAERS mining), not
       asserted in free text.
    3. Literature monitoring — literature signals should reconcile against the
       controlled literature-monitoring system.
    4. PSUR / labeling-change workflow — a signal never updates labeling except
       through the controlled labeling-change / PSUR workflow; this workflow does
       not file.
    5. Qualified approver gate — every AI-suggested determination must be
       reviewed and confirmed by a qualified Pharmacovigilance / Safety
       Physician; output is never a signal determination of record.
    6. Dedicated third-model signal auditor — production should use a separately
       configured auditor model for signal-strength bias detection. See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import (
    extract_flags,
    extract_veto_directive,
    sanitize_for_prompt,
    truncate_flag_display,
)
from ...core.workflow import BaseWorkflow, WorkflowResult

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated pharmacovigilance signal evaluation is "
    "decision-support, not a signal determination and not a regulatory filing. A "
    "qualified Pharmacovigilance / Safety Physician must independently confirm "
    "signal strength, causality, and labeling impact before any signal is closed "
    "or escalated. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "signal meeting the threshold for regulatory action / label change "
    "characterized as no-action. See metadata['veto_reason']. Escalate to the "
    "Safety Physician / QPPV; the signal requires formal evaluation and likely a "
    "labeling / regulatory action."
)

_FLAG_HEADERS = ("SIGNAL-STRENGTH FLAGS:", "CAUSALITY FLAGS:", "LABELING-IMPACT FLAGS:")

_PV_SIGNAL_REVIEW_CRITERIA = """\
Evaluate this pharmacovigilance signal evaluation on five dimensions. Score each 0–10.

1. SIGNAL STRENGTH (30%) — CRITICAL
   Is the signal strength correctly characterized against the disproportionality
   metrics and case evidence? Penalise a signal strength understated relative to
   the evidence. Flag under SIGNAL-STRENGTH FLAGS:.

2. CAUSALITY ASSESSMENT (25%) — CRITICAL
   Is population-level causality assessed with an adequate basis (not dismissed)?
   Penalise causality dismissed without adequate justification. Flag under
   CAUSALITY FLAGS:.

3. LABELING/REGULATORY IMPACT (20%) — CRITICAL
   Does the proposed action reflect the labeling / regulatory implication of the
   signal? Penalise a labeling / regulatory-action implication the proposed
   action does not reflect. Flag under LABELING-IMPACT FLAGS:.

4. BENEFIT-RISK / DATA-SOURCE ADEQUACY (15%)
   Is the data source adequate for the conclusion and the benefit-risk framing
   sound? Penalise a conclusion the data source cannot support.

5. ACTIONABILITY (10%)
   Is the evaluation specific enough to act on (signal, metric, action)? Penalise
   vague evaluations.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a signal meeting the threshold for regulatory action / label
change is characterized as no-action / routine.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SIGNAL-STRENGTH FLAGS AND zero CAUSALITY FLAGS AND zero
LABELING-IMPACT FLAGS AND no VETO: ready for Safety Physician sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SIGNAL-STRENGTH FLAGS: [bullet list, or "None detected"]
  CAUSALITY FLAGS: [bullet list, or "None detected"]
  LABELING-IMPACT FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are producing a pharmacovigilance signal evaluation for a qualified
Pharmacovigilance / Safety Physician. You have no stake in the outcome. Your job
is to characterize the signal strength, assess population-level causality, judge
the labeling / regulatory impact, and evaluate the proposed action — grounded
only in the data supplied.

BASE THE EVALUATION ON THE INPUT DATA ONLY.

SAFETY-SIGNAL DATA:
{request_text}

{wiki_context}

Produce a structured evaluation with exactly these sections:

## Signal summary
Summarise the signal, the product, and the data source from the input.

## Signal strength
Characterize the signal strength against the disproportionality metrics and case
evidence. Do not understate a signal the evidence supports.

## Causality assessment
Assess population-level causality with an explicit basis; do not dismiss
causality without justification.

## Labeling / regulatory impact
State whether the signal implies a labeling change or regulatory action, and
whether the proposed action reflects it.

## Recommended action
State the recommended action (routine monitoring, formal evaluation, labeling
change, regulatory notification) and its basis.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this pharmacovigilance signal evaluation. Address EVERY issue in the
reviewer's critique, especially any SIGNAL-STRENGTH FLAGS, CAUSALITY FLAGS, or
LABELING-IMPACT FLAGS.

PREVIOUS EVALUATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SIGNAL-STRENGTH flag: re-characterize the signal against the metrics.
⚠️  For any CAUSALITY flag: re-assess population-level causality with a basis.
⚠️  For any LABELING-IMPACT flag: reflect the labeling / regulatory implication in
the action.
"""


@dataclass
class PVSignalRequest:
    """Structured input for the pharmacovigilance signal evaluation workflow."""

    product_description: str
    """Generic product category and its market status."""

    signal_description: str
    """The observed signal / adverse-event-of-interest."""

    data_source: str
    """Data source: spontaneous DB / literature / disproportionality run."""

    case_series_summary: str
    """Aggregate case count and features for the signal."""

    disproportionality_metrics: str
    """Disproportionality metrics (PRR / ROR / EBGM)."""

    causality_assessment: str
    """Caller's population-level causality assessment."""

    current_labeling: str
    """Whether the event is already in the product labeling."""

    proposed_action: str
    """Caller's proposed action (routine / no-action / label change)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Signal description: {self.signal_description[:cap]}",
            f"Data source: {self.data_source[:cap]}",
            f"Case series summary: {self.case_series_summary[:cap]}",
            f"Disproportionality metrics: {self.disproportionality_metrics[:cap]}",
            f"Causality assessment: {self.causality_assessment[:cap]}",
            f"Current labeling: {self.current_labeling[:cap]}",
            f"Proposed action: {self.proposed_action[:cap]}",
        ])


class PharmacovigilanceSignalWorkflow(BaseWorkflow):
    """
    Adversarial pharmacovigilance signal evaluation: executor evaluates an
    aggregate signal → reviewer challenges understated signal strength, dismissed
    causality, and unreflected labeling impact, with the power to VETO → iterate.

    BOUNDARY (D-LIFESCI-2): distinct from the healthcare
    AdverseEventTriageWorkflow — that grades clinical severity/causality for a
    single adverse event for a provider; this evaluates an aggregate safety
    signal and its labeling / regulatory impact for the marketing-authorization
    holder.

    Convergence gate (D-LIFESCI-4):
        score ≥ threshold (8.0)
        AND zero SIGNAL-STRENGTH FLAGS
        AND zero CAUSALITY FLAGS
        AND zero LABELING-IMPACT FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: PVSignalRequest,
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
        veto_reason: str | None = None
        max_wiki_chars = config.max_wiki_body_chars

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    request_text=request_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                flag_section = self._format_flag_section(current)
                prompt = _REVISION_PROMPT.format(
                    previous=sanitize_for_prompt(output, max_chars=10000),
                    score=f"{score:.1f}",
                    critique=sanitize_for_prompt(review.critique, max_chars=4000),
                    suggestions="\n".join(
                        f"- {sanitize_for_prompt(s, max_chars=500)}"
                        for s in review.suggestions
                    ),
                    flag_section=flag_section,
                    wiki_context=wiki_ctx,
                )

            output = await self.executor.run(prompt, context="")
            self._register_claims(output, round_num)

            review = await self.reviewer.review(
                output,
                criteria=_PV_SIGNAL_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            # Audit-trail writes happen BEFORE the veto check — preserves the
            # round-N draft in wiki + ledger even if vetoed (D-LIFESCI-4).
            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            veto_reason = self._extract_veto(review.critique, max_wiki_chars)
            if veto_reason is not None:
                break

            if review.approved and not self._flag_classes_unresolved(
                review.critique, _FLAG_HEADERS, current.values()
            ):
                converged = True
                break

        pv_signal_checklist = self._build_pv_signal_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "signal_strength_flags": list(
                dict.fromkeys(accumulated["SIGNAL-STRENGTH FLAGS:"])
            ),
            "causality_flags": list(dict.fromkeys(accumulated["CAUSALITY FLAGS:"])),
            "labeling_impact_flags": list(
                dict.fromkeys(accumulated["LABELING-IMPACT FLAGS:"])
            ),
            "pv_signal_checklist": pv_signal_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the Safety Physician sees what the AI produced before the REVIEWER
            # VETO banner was prepended.
            # L-HEALTH-1: this field may echo sanitized caller data
            # (signal_description, case_series_summary) that can carry patient
            # PHI. Callers must apply downstream PHI handling before logging or
            # sharing.
            metadata["first_draft"] = output

        return WorkflowResult(
            output=output_with_banner,
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata=metadata,
        )

    @staticmethod
    def _extract_veto(critique: str, max_chars: int) -> str | None:
        """Thin delegate to `core._internal.extract_veto_directive`
        (M-PC-1 / M2 / L5 hardening). Test API preserved."""
        return extract_veto_directive(critique, "REVIEWER VETO:", max_chars)

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "SIGNAL-STRENGTH FLAGS:": (
                "⚠️  SIGNAL-STRENGTH FLAGS (re-characterize the signal against the "
                "metrics):"
            ),
            "CAUSALITY FLAGS:": (
                "⚠️  CAUSALITY FLAGS (re-assess population-level causality with a "
                "basis):"
            ),
            "LABELING-IMPACT FLAGS:": (
                "⚠️  LABELING-IMPACT FLAGS (reflect the labeling / regulatory "
                "implication in the action):"
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
    def _compose_output(draft: str, veto_reason: str | None) -> str:
        if veto_reason is None:
            return f"{draft}\n\n---\n\n{_DISCLAIMER}"
        return (
            f"{_VETO_BANNER}\n\nVETO DIRECTIVE: {veto_reason}\n\n"
            f"--- Vetoed draft below ---\n\n{draft}\n\n---\n\n{_DISCLAIMER}"
        )

    @staticmethod
    def _build_pv_signal_checklist(
        request: PVSignalRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Pharmacovigilance / Safety Physician]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — a signal meeting the threshold for "
                "regulatory action is characterized as no-action; escalate to the "
                "Safety Physician / QPPV for formal evaluation and likely labeling "
                "action"
            )
        signal_strength_flags = accumulated.get("SIGNAL-STRENGTH FLAGS:", [])
        causality_flags = accumulated.get("CAUSALITY FLAGS:", [])
        labeling_impact_flags = accumulated.get("LABELING-IMPACT FLAGS:", [])
        if signal_strength_flags:
            checklist.append(
                f"[ ] ⚠️  SIGNAL-STRENGTH FLAGS ({len(signal_strength_flags)}) — "
                "re-characterize the signal against the metrics"
            )
        if causality_flags:
            checklist.append(
                f"[ ] ⚠️  CAUSALITY FLAGS ({len(causality_flags)}) — re-assess "
                "population-level causality with a basis"
            )
        if labeling_impact_flags:
            checklist.append(
                f"[ ] ⚠️  LABELING-IMPACT FLAGS ({len(labeling_impact_flags)}) — "
                "reflect the labeling / regulatory implication in the action"
            )
        checklist.extend([
            "[ ] Re-characterize the signal strength against the disproportionality metrics",
            "[ ] Re-assess population-level causality with an explicit basis",
            "[ ] Reflect any labeling / regulatory implication in the action",
            "[ ] Route any labeling change through the controlled PSUR / labeling workflow",
            "[ ] Obtain Pharmacovigilance / Safety Physician sign-off before the "
            "signal is closed",
        ])
        return checklist
