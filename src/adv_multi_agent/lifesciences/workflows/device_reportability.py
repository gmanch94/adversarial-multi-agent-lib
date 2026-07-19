"""
Workflow — Device Reportability / MDR Determination (Lifesciences · Devices
post-market, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to medical-device
post-market reportability: executor produces a reportability determination for a
device complaint (reportable vs non-reportable, outcome grade, trend basis,
statutory clock); reviewer (cross-model per ARIS §2.1) challenges any
under-grading of the outcome, any masked malfunction trend, and any incorrect
clock, with the power to VETO when a 'non-reportable' determination is actually
reportable under the applicable regulation.

BOUNDARY (D-LIFESCI-2): distinct from the healthcare AdverseEventTriageWorkflow —
that workflow grades clinical severity/causality for a provider; this decides the
manufacturer's regulatory reportability (21 CFR 803 MDR / regional vigilance) and
statutory clock.

Veto gate (D-LIFESCI-3): fires when a 'non-reportable' determination is actually
reportable under the applicable regulation (21 CFR 803 / regional vigilance) —
such that failing to report would breach the statutory clock.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Complaint-handling system — complaints and their handling state should
       resolve against the controlled complaint-handling QMS, not
       caller-pasted narrative text.
    2. FDA eMDR — reportable events must be filed through the FDA electronic
       Medical Device Reporting (eMDR) gateway; this workflow does not file.
    3. EU EUDAMED vigilance — regional vigilance reporting should reconcile
       against the EUDAMED vigilance module; this workflow does not submit.
    4. Reportability decision-tree engine — the reporting definition should be
       applied by the controlled reportability decision-tree engine, not
       caller-supplied free text.
    5. Dedicated third-model trend auditor — production should use a separately
       configured auditor model for malfunction-trend / threshold detection.
       See ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated device-reportability determination is "
    "decision-support, not a regulatory filing. A qualified Post-market "
    "Surveillance / Vigilance officer must independently confirm reportability "
    "and the statutory clock under 21 CFR 803 / regional vigilance before any "
    "decision to report or not report. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "'non-reportable' determination that is actually reportable under the "
    "applicable regulation. See metadata['veto_reason']. Escalate to the "
    "Vigilance officer; initiate the report within the statutory clock."
)

_FLAG_HEADERS = ("REPORTABILITY FLAGS:", "SERIOUS-INJURY FLAGS:", "MALFUNCTION-TREND FLAGS:")

_REPORTABILITY_REVIEW_CRITERIA = """\
Evaluate this device-reportability determination on five dimensions. Score each 0–10.

1. REPORTABILITY DETERMINATION (30%) — CRITICAL
   Does the event meet a reporting definition (death, serious injury, or a
   malfunction likely to cause/contribute to death or serious injury if it
   recurs)? Penalise a reportable event coded non-reportable. Flag under
   REPORTABILITY FLAGS:.

2. OUTCOME GRADING (25%) — CRITICAL
   Is the outcome graded correctly — is a reportable serious injury under-graded
   as minor? Penalise under-grading of patient impact. Flag under
   SERIOUS-INJURY FLAGS:.

3. MALFUNCTION TREND (20%) — CRITICAL
   Does a recurring malfunction cross a trend / threshold reporting trigger that
   the single event masks? Penalise a trend the determination ignores. Flag
   under MALFUNCTION-TREND FLAGS:.

4. REGULATORY-CLOCK FIT (15%)
   Is the statutory clock correct for the determination (21 CFR 803 timelines /
   regional vigilance)? Penalise an incorrect or unstated clock.

5. ACTIONABILITY (10%)
   Is the determination specific enough to act on (report path, clock, trend
   basis)? Penalise vague determinations.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a 'non-reportable' determination is actually reportable under
the applicable regulation (21 CFR 803 / regional vigilance).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero REPORTABILITY FLAGS AND zero SERIOUS-INJURY FLAGS AND
zero MALFUNCTION-TREND FLAGS AND no VETO: ready for Vigilance officer sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  REPORTABILITY FLAGS: [bullet list, or "None detected"]
  SERIOUS-INJURY FLAGS: [bullet list, or "None detected"]
  MALFUNCTION-TREND FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are producing a medical-device reportability determination for a qualified
Post-market Surveillance / Vigilance officer. You have no stake in the outcome.
Your job is to decide whether the complaint is reportable under the applicable
regulation (21 CFR 803 MDR / regional vigilance), grade the outcome, account for
any malfunction trend, and state the statutory clock — grounded only in the data
supplied.

BASE THE DETERMINATION ON THE INPUT DATA ONLY.

DEVICE-COMPLAINT DATA:
{request_text}

{wiki_context}

Produce a structured reportability determination with exactly these sections:

## Event summary
Summarise the complaint, the device, and the reported outcome from the input.

## Reportability determination
Apply the reporting definition (death, serious injury, or malfunction likely to
cause/contribute to death or serious injury if it recurs). State whether the
event is reportable or non-reportable and why.

## Outcome grading
Grade the patient impact against the definition. State whether the outcome is a
reportable serious injury; do not under-grade a reportable outcome as minor.

## Malfunction-trend assessment
Account for prior_similar_events_count against any trend / threshold reporting
trigger. State whether a recurring malfunction the single event masks is itself
reportable.

## Statutory clock and report path
State the statutory clock (21 CFR 803 timelines / regional vigilance) and the
report path for each market region.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this device-reportability determination. Address EVERY issue in the
reviewer's critique, especially any REPORTABILITY FLAGS, SERIOUS-INJURY FLAGS, or
MALFUNCTION-TREND FLAGS.

PREVIOUS DETERMINATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any REPORTABILITY flag: re-apply the reporting definition and state the
clock.
⚠️  For any SERIOUS-INJURY flag: re-grade the outcome against the definition.
⚠️  For any MALFUNCTION-TREND flag: account for prior_similar_events_count against
the trend trigger.
"""


@dataclass
class ReportabilityRequest:
    """Structured input for the device-reportability determination workflow."""

    complaint_narrative: str
    """The complaint narrative: what happened, the device, the reported outcome."""

    device_identifier: str
    """Generic device category and identifier (e.g. an infusion pump, model class)."""

    event_outcome: str
    """The reported clinical outcome of the event."""

    patient_impact: str
    """The stated patient impact / harm and its current grading."""

    malfunction_recurrence_potential: str
    """Whether the malfunction could recur and its likely consequence if it does."""

    prior_similar_events_count: str
    """Count / description of prior similar events for trend assessment."""

    market_regions: str
    """Market regions where the device is distributed (drives the report path)."""

    date_became_aware: str
    """The date the manufacturer became aware (starts the statutory clock)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Complaint narrative: {self.complaint_narrative[:cap]}",
            f"Device identifier: {self.device_identifier[:cap]}",
            f"Event outcome: {self.event_outcome[:cap]}",
            f"Patient impact: {self.patient_impact[:cap]}",
            f"Malfunction recurrence potential: {self.malfunction_recurrence_potential[:cap]}",
            f"Prior similar events count: {self.prior_similar_events_count[:cap]}",
            f"Market regions: {self.market_regions[:cap]}",
            f"Date became aware: {self.date_became_aware[:cap]}",
        ])


class DeviceReportabilityWorkflow(BaseWorkflow):
    """
    Adversarial device-reportability determination: executor decides whether a
    complaint is reportable → reviewer challenges under-graded outcomes, masked
    malfunction trends, and incorrect clocks, with the power to VETO → iterate.

    BOUNDARY (D-LIFESCI-2): distinct from the healthcare
    AdverseEventTriageWorkflow — that grades clinical severity/causality for a
    provider; this decides the manufacturer's regulatory reportability (21 CFR
    803 MDR / regional vigilance) and statutory clock.

    Convergence gate (D-LIFESCI-3):
        score ≥ threshold (8.0)
        AND zero REPORTABILITY FLAGS
        AND zero SERIOUS-INJURY FLAGS
        AND zero MALFUNCTION-TREND FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: ReportabilityRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_reportability_flags: list[str] = []
        current_serious_injury_flags: list[str] = []
        current_malfunction_trend_flags: list[str] = []
        all_reportability_flags: list[str] = []
        all_serious_injury_flags: list[str] = []
        all_malfunction_trend_flags: list[str] = []
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
                flag_section = self._format_flag_section(
                    current_reportability_flags,
                    current_serious_injury_flags,
                    current_malfunction_trend_flags,
                )
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
                criteria=_REPORTABILITY_REVIEW_CRITERIA,
            )
            score = review.score
            current_reportability_flags = extract_flags(review.critique, "REPORTABILITY FLAGS:")
            current_serious_injury_flags = extract_flags(review.critique, "SERIOUS-INJURY FLAGS:")
            current_malfunction_trend_flags = extract_flags(
                review.critique, "MALFUNCTION-TREND FLAGS:"
            )
            all_reportability_flags.extend(current_reportability_flags)
            all_serious_injury_flags.extend(current_serious_injury_flags)
            all_malfunction_trend_flags.extend(current_malfunction_trend_flags)

            # Audit-trail writes happen BEFORE the veto check — preserves the
            # round-N draft in wiki + ledger even if vetoed (D-LIFESCI-3).
            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            veto_reason = self._extract_veto(review.critique, max_wiki_chars)
            if veto_reason is not None:
                break

            if (
                review.approved
                and not current_reportability_flags
                and not current_serious_injury_flags
                and not current_malfunction_trend_flags
            ):
                converged = True
                break

        reportability_checklist = self._build_reportability_checklist(
            request,
            {
                "REPORTABILITY FLAGS:": all_reportability_flags,
                "SERIOUS-INJURY FLAGS:": all_serious_injury_flags,
                "MALFUNCTION-TREND FLAGS:": all_malfunction_trend_flags,
            },
            veto_reason,
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "device_identifier": sanitize_for_prompt(
                request.device_identifier, max_chars=200
            ),
            "reportability_flags": list(dict.fromkeys(all_reportability_flags)),
            "serious_injury_flags": list(dict.fromkeys(all_serious_injury_flags)),
            "malfunction_trend_flags": list(dict.fromkeys(all_malfunction_trend_flags)),
            "reportability_checklist": reportability_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the Vigilance officer sees what the AI produced before the REVIEWER
            # VETO banner was prepended.
            # L-HEALTH-1: this field may echo sanitized caller data
            # (complaint_narrative, patient_impact) that can carry patient PHI.
            # Callers must apply downstream PHI handling before logging or sharing.
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
    def _format_flag_section(
        reportability_flags: list[str],
        serious_injury_flags: list[str],
        malfunction_trend_flags: list[str],
    ) -> str:
        if (
            not reportability_flags
            and not serious_injury_flags
            and not malfunction_trend_flags
        ):
            return ""
        parts: list[str] = []
        if reportability_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(reportability_flags)
            )
            parts.append(
                "⚠️  REPORTABILITY FLAGS (re-apply the reporting definition and "
                "state the clock):\n"
                f"{flags_text}"
            )
        if serious_injury_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(serious_injury_flags)
            )
            parts.append(
                "⚠️  SERIOUS-INJURY FLAGS (re-grade the outcome against the "
                "definition):\n"
                f"{flags_text}"
            )
        if malfunction_trend_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(malfunction_trend_flags)
            )
            parts.append(
                "⚠️  MALFUNCTION-TREND FLAGS (account for prior similar events "
                "against the trend trigger):\n"
                f"{flags_text}"
            )
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
    def _build_reportability_checklist(
        request: ReportabilityRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Post-market Surveillance / Vigilance Officer]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — a 'non-reportable' determination is "
                "actually reportable; escalate to the Vigilance officer and "
                "initiate the report within the statutory clock"
            )
        reportability_flags = accumulated.get("REPORTABILITY FLAGS:", [])
        serious_injury_flags = accumulated.get("SERIOUS-INJURY FLAGS:", [])
        malfunction_trend_flags = accumulated.get("MALFUNCTION-TREND FLAGS:", [])
        if reportability_flags:
            checklist.append(
                f"[ ] ⚠️  REPORTABILITY FLAGS ({len(reportability_flags)}) — "
                "re-apply the reporting definition and state the clock for each"
            )
        if serious_injury_flags:
            checklist.append(
                f"[ ] ⚠️  SERIOUS-INJURY FLAGS ({len(serious_injury_flags)}) — "
                "re-grade the outcome against the definition"
            )
        if malfunction_trend_flags:
            checklist.append(
                f"[ ] ⚠️  MALFUNCTION-TREND FLAGS ({len(malfunction_trend_flags)}) — "
                "evaluate the trend against prior similar events"
            )
        checklist.extend([
            "[ ] Re-apply the reporting definition and state the statutory clock",
            "[ ] Re-grade the outcome against the serious-injury definition",
            "[ ] Evaluate the malfunction trend against prior similar events",
            "[ ] File within the statutory clock for each affected market region",
            "[ ] Obtain Vigilance officer sign-off before the determination is closed",
        ])
        return checklist
