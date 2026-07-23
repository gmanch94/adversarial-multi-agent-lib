"""
Workflow — Adverse Event Triage (Healthcare Teaching Example — Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to pharmacovigilance
adverse-event triage: executor grades severity, assesses causality, and
determines regulatory reporting obligations; reviewer (cross-model per ARIS
§2.1) challenges CTCAE grading, causality-scale application, and regulatory
clock accuracy, with the power to VETO when a serious unexpected ADR triggering
an expedited regulatory report is identified.

Veto gate (D-HEALTH-4): fires on serious unexpected ADR with causality ≥
possible (15-day expedited report), fatal or life-threatening outcome with
causality ≥ probable (7-day expedited report), or life-threatening outcome
with causality ≥ possible (7-day clock per ICH E2A / FDA 21 CFR 312 / EMA
EudraVigilance).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PHI de-identification — caller is responsible for stripping PHI
       before passing patient_demographics and event_description to this
       workflow.
    2. Safety database integration (FAERS, EudraVigilance, sponsor safety DB)
       — no live database query or auto-submission is performed.
    3. MedWatch / EudraVigilance filing automation — output is advisory only;
       a qualified pharmacovigilance officer must initiate the actual report.
    4. MedDRA coding validation — preferred-term and system-organ-class coding
       must be verified by a qualified medical coder; AI coding is indicative.
    5. Sponsor SUSAR notification automation (ICH E2A) — SUSAR distribution to
       regulatory agencies and investigators is not automated here.
    6. Dedicated third-model causality auditor — see ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated adverse-event triage is not a regulatory "
    "report. A qualified pharmacovigilance officer or drug-safety scientist must "
    "independently verify severity, causality, and labeling status, and file the "
    "MedWatch / EudraVigilance report. AI output must never substitute for "
    "qualified-physician causality assessment."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer identified "
    "a serious adverse event that triggers a mandatory expedited regulatory report. "
    "See metadata['veto_reason']. Escalate to pharmacovigilance officer; initiate "
    "MedWatch / EudraVigilance filing within the regulatory clock."
)

_FLAG_HEADERS = ("SEVERITY FLAGS:", "CAUSALITY FLAGS:", "REGULATORY FLAGS:")

_ADVERSE_EVENT_REVIEW_CRITERIA = """\
Evaluate this adverse-event triage on five dimensions. Score each 0–10.

1. SEVERITY GRADING (30%) — CRITICAL
   Is the event graded against CTCAE / ICH E2A definitions, NOT general
   practice intuition? Are grade assignments consistent with reporter's
   narrative? Penalise severity claims not anchored to CTCAE or ICH E2A.
   Flag gaps under SEVERITY FLAGS:.

2. CAUSALITY ASSESSMENT (25%) — CRITICAL
   Is WHO-UMC or Naranjo causality scale applied? Are specific criteria cited
   (temporal relationship, dechallenge/rechallenge, alternative cause ruled
   out)? Penalise causality assertions not grounded in a named scale.
   Flag gaps under CAUSALITY FLAGS:.

3. REGULATORY-OBLIGATION FIT (20%) — CRITICAL
   Is the reporting obligation matched to FDA 21 CFR 312 / EMA EudraVigilance /
   ICH E2A reporting clock? (7-day for fatal/life-threatening unexpected;
   15-day for other serious unexpected.) Does the triage correctly identify
   whether the ADR is in current labeling? Flag gaps under REGULATORY FLAGS:.

4. MedDRA CODING ACCURACY (15%)
   Is the preferred-term / system-organ-class alignment plausible for the
   event described? Penalise PT/SOC combinations that conflict with the
   event narrative.

5. ACTIONABILITY (10%)
   Is the report path and regulatory clock specified? Vague recommendations
   ("report as required") should be flagged.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Serious unexpected ADR (not in current product labeling per prior_reports)
    with causality ≥ possible → mandatory FDA 21 CFR 312 / EMA EudraVigilance
    expedited report required (15-day clock for serious unexpected; 7-day
    for fatal/life-threatening unexpected per ICH E2A).
  • Fatal outcome with causality ≥ possible AND event not in current
    labeling → 7-day expedited reporting clock.
  • Life-threatening outcome with causality ≥ probable → 7-day expedited
    reporting clock.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those
  as stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score ≥ 8.0 AND zero SEVERITY FLAGS AND zero CAUSALITY FLAGS AND zero
REGULATORY FLAGS AND no VETO: triage is ready for pharmacovigilance officer
sign-off. Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SEVERITY FLAGS: [bullet list, or "None detected"]
  CAUSALITY FLAGS: [bullet list, or "None detected"]
  REGULATORY FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are conducting an adverse-event triage for a qualified pharmacovigilance
officer to review. You have no stake in the outcome. Your job is to grade
severity, assess causality, determine regulatory reporting obligations, and
propose MedDRA coding for the reported event, grounded only in the data
supplied.

BASE THE TRIAGE ON THE INPUT DATA ONLY.

ADVERSE EVENT DATA:
{request_text}

{wiki_context}

Produce a structured adverse-event triage with exactly these sections:

## Severity assessment
Grade the event against CTCAE / ICH E2A definitions. State the grade and
definition used. For fatal events: CTCAE Grade 5. For life-threatening:
CTCAE Grade 4.

## Causality analysis
Apply WHO-UMC or Naranjo causality scale. Cite the specific criterion met
(temporal relationship, dechallenge/rechallenge, alternative cause). State
the causality category (certain / probable / possible / unlikely / unassessable).

## Regulatory-obligation determination
Determine whether the ADR is in current labeling (per prior_reports). State
the applicable reporting clock: 7-day (fatal/life-threatening unexpected) or
15-day (other serious unexpected) per FDA 21 CFR 312 / EMA EudraVigilance /
ICH E2A. If not reportable, state why.

## MedDRA coding
Propose Preferred Term (PT) and System Organ Class (SOC) for the event.
Include MedDRA code if known.

## Recommended action
Specify the report path (MedWatch / EudraVigilance / both), regulatory clock,
and any sponsor SUSAR notification obligation under ICH E2A.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this adverse-event triage. Address EVERY issue in the reviewer's
critique, especially any SEVERITY FLAGS, CAUSALITY FLAGS, or REGULATORY FLAGS.

PREVIOUS TRIAGE:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SEVERITY FLAG: re-grade against CTCAE / ICH E2A definitions;
do not use general practice intuition.
⚠️  For any CAUSALITY FLAG: cite the specific WHO-UMC or Naranjo criterion
(temporal, dechallenge, rechallenge, alternative cause).
⚠️  For any REGULATORY FLAG: match obligation to FDA 21 CFR 312 / EMA
EudraVigilance / ICH E2A reporting clock explicitly.
"""


@dataclass
class AdverseEventRequest:
    """Structured input for the adverse-event triage workflow."""

    product_name: str
    """Name and formulation of the suspect product."""

    event_description: str
    """Narrative description of the adverse event from the reporter."""

    patient_demographics: str
    """De-identified patient demographics (age, sex, weight, relevant history)."""

    event_onset: str
    """Date/time of event onset relative to product exposure."""

    causality_assessment: str
    """Reporter's or clinician's initial causality assessment."""

    concomitant_medications: str
    """List of concomitant medications at the time of the event."""

    outcome: str
    """Event outcome (recovered, fatal, life-threatening, hospitalized, etc.)."""

    prior_reports: str
    """Labeling status: is this event in current USPI / SmPC? Prior safety database reports."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product name: {self.product_name[:cap]}",
            f"Event description: {self.event_description[:cap]}",
            f"Patient demographics: {self.patient_demographics[:cap]}",
            f"Event onset: {self.event_onset[:cap]}",
            f"Causality assessment: {self.causality_assessment[:cap]}",
            f"Concomitant medications: {self.concomitant_medications[:cap]}",
            f"Outcome: {self.outcome[:cap]}",
            f"Prior reports: {self.prior_reports[:cap]}",
        ])


class AdverseEventTriageWorkflow(BaseWorkflow):
    """
    Adversarial adverse-event triage: executor grades severity, assesses
    causality, and determines regulatory obligations → reviewer challenges
    CTCAE grading, causality-scale application, and regulatory clock accuracy,
    with the power to VETO → iterate.

    Convergence gate (D-HEALTH-2 / D-HEALTH-4):
        score ≥ threshold (8.0)
        AND zero SEVERITY FLAGS
        AND zero CAUSALITY FLAGS
        AND zero REGULATORY FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: AdverseEventRequest,
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
                criteria=_ADVERSE_EVENT_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            # Audit-trail writes happen BEFORE the veto check — preserves the
            # round-N draft in wiki + ledger even if vetoed (D-HEALTH-2).
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

        adverse_event_checklist = self._build_adverse_event_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_name": sanitize_for_prompt(
                request.product_name, max_chars=200
            ),
            "severity_flags": list(dict.fromkeys(accumulated["SEVERITY FLAGS:"])),
            "causality_flags": list(dict.fromkeys(accumulated["CAUSALITY FLAGS:"])),
            "regulatory_flags": list(dict.fromkeys(accumulated["REGULATORY FLAGS:"])),
            "adverse_event_checklist": adverse_event_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round
            # so the pharmacovigilance officer sees what the AI produced before
            # the REVIEWER VETO banner was prepended.
            # L-HEALTH-1: this field may echo sanitized PHI from prompt-supplied
            # caller data (patient_demographics, event_description). Callers
            # must apply downstream PHI handling before logging or sharing.
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
            "SEVERITY FLAGS:": (
                "⚠️  SEVERITY FLAGS (grade severity against CTCAE / ICH E2A "
                "definitions; do not infer beyond reporter's narrative):"
            ),
            "CAUSALITY FLAGS:": (
                "⚠️  CAUSALITY FLAGS (use WHO-UMC or Naranjo causality scale; "
                "cite the specific criterion (temporal, dechallenge, rechallenge, "
                "alternative cause)):"
            ),
            "REGULATORY FLAGS:": (
                "⚠️  REGULATORY FLAGS (match obligation to FDA 21 CFR 312 / EMA "
                "EudraVigilance / ICH E2A reporting clock (7-day for "
                "fatal+life-threatening unexpected; 15-day for other serious "
                "unexpected)):"
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
    def _build_adverse_event_checklist(
        request: AdverseEventRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = [
            "[OWNER: Pharmacovigilance Officer / Drug Safety Scientist]"
        ]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — initiate MedWatch / EudraVigilance "
                "expedited filing within regulatory clock"
            )
        severity_flags = accumulated.get("SEVERITY FLAGS:", [])
        causality_flags = accumulated.get("CAUSALITY FLAGS:", [])
        regulatory_flags = accumulated.get("REGULATORY FLAGS:", [])
        if severity_flags:
            checklist.append(
                f"[ ] ⚠️  SEVERITY FLAGS ({len(severity_flags)}) — re-grade "
                "against CTCAE / ICH E2A definitions"
            )
        if causality_flags:
            checklist.append(
                f"[ ] ⚠️  CAUSALITY FLAGS ({len(causality_flags)}) — apply "
                "WHO-UMC or Naranjo scale with documented criteria"
            )
        if regulatory_flags:
            checklist.append(
                f"[ ] ⚠️  REGULATORY FLAGS ({len(regulatory_flags)}) — confirm "
                "reporting clock against FDA 21 CFR 312 / EMA EudraVigilance / ICH E2A"
            )
        checklist.extend([
            "[ ] Verify MedDRA PT/SOC coding for event_description",
            "[ ] Confirm causality assessment via WHO-UMC or Naranjo with documented criteria",
            "[ ] Confirm labeling status against current USPI / SmPC / sponsor safety database",
            "[ ] Notify sponsor / SUSAR-relevant parties per ICH E2A if clinical trial",
            "[ ] File final report and document in safety database",
        ])
        return checklist
