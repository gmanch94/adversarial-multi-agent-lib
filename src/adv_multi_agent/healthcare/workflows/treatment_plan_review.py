"""
Workflow — Treatment Plan Review (Healthcare Teaching Example — Veto)
Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to clinical
treatment-plan review: executor grounds the plan in clinical guidelines,
checks drug-allergy / drug-organ-failure / procedure-condition
contraindications, and stratifies patient-specific risk; reviewer
(cross-model per ARIS §2.1) challenges guideline citations, contraindication
completeness, and risk stratification, with the power to VETO when an
absolute contraindication requiring physician escalation is identified.

Veto gate (D-HEALTH-4): fires on absolute drug-allergy contraindication,
drug-organ-failure contraindication, or procedure contraindicated given
documented comorbidity or medication.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PHI de-identification — caller is responsible for stripping PHI
       before passing patient_summary and other fields to this workflow.
    2. EHR integration — Epic/Cerner medication reconciliation, allergy list,
       and lab values must be pulled from the live EHR before invocation.
    3. Live drug knowledge base (Lexicomp, Micromedex) for contraindication
       checking — no live database query is performed here.
    4. Physician sign-off gate — no plan executes without attending physician
       order entry; this workflow is advisory only.
    5. Pharmacy verification — pharmacist verification required before
       dispensing any medication orders.
    6. Dedicated third-model contraindication auditor — see ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated treatment-plan review is not a prescription "
    "or order set. An attending physician must independently verify guideline grounding, "
    "contraindication completeness, and risk against the patient's full record before "
    "any order entry. AI output must never trigger automated prescribing or procedural "
    "scheduling."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted. The reviewer identified an absolute "
    "contraindication that requires physician escalation BEFORE any prescribing "
    "decision. See metadata['veto_reason']. Escalate to attending physician."
)

_FLAG_HEADERS = ("GUIDELINE FLAGS:", "CONTRAINDICATION FLAGS:", "RISK FLAGS:")

_TREATMENT_PLAN_REVIEW_CRITERIA = """\
Evaluate this treatment-plan review on five dimensions. Score each 0–10.

1. GUIDELINE GROUNDING (30%) — CRITICAL
   Is every clinical claim grounded in a cited guideline? Citations must name
   the guideline document and section, not just summarise conclusions.
   Penalise claims not anchored to a named guideline with a section reference.
   Flag gaps under GUIDELINE FLAGS:.

2. CONTRAINDICATION COMPLETENESS (25%) — CRITICAL
   Are drug-allergy, drug-organ-failure, and procedure-condition
   contraindications fully checked? Is each contraindication mechanism named
   (not just asserted)? Penalise reviews that assert "no contraindications"
   without checking allergy history, organ function (eGFR, liver function),
   and procedure-comorbidity pairs.
   Flag gaps under CONTRAINDICATION FLAGS:.

3. RISK STRATIFICATION (20%) — CRITICAL
   Is risk stratified against patient-specific factors (age, comorbidity, lab
   values) rather than baseline-population risk? Is the numeric basis cited
   (e.g. eGFR value, Child-Pugh score)?
   Flag gaps under RISK FLAGS:.

4. DOSE/ROUTE/DURATION SPECIFICITY (15%)
   Are exact doses, routes, and durations specified? Vague recommendations
   ("start a statin") must be flagged as insufficient for order entry.

5. ACTIONABILITY (10%)
   Can the attending physician execute or reject this plan directly? Vague
   recommendations ("consider cardiology consult") that lack a decision
   criterion must be flagged.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Absolute drug-allergy contraindication present in patient_summary or
    contraindication_context (e.g. documented anaphylaxis to penicillin,
    proposed plan includes penicillin-class antibiotic).
  • Drug-organ-failure contraindication (e.g. renally-cleared drug at full
    dose with eGFR below the guideline threshold; hepatotoxic drug in
    Child-Pugh C cirrhosis).
  • Procedure in proposed_plan is contraindicated given documented
    comorbidity or medication (e.g. contrast-enhanced procedure in CKD3
    without prophylaxis; elective surgery on anticoagulated patient
    without bridging plan).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those
  as stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score ≥ 8.0 AND zero GUIDELINE FLAGS AND zero CONTRAINDICATION FLAGS AND zero
RISK FLAGS AND no VETO: plan is ready for attending physician sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  GUIDELINE FLAGS: [bullet list, or "None detected"]
  CONTRAINDICATION FLAGS: [bullet list, or "None detected"]
  RISK FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are conducting a treatment-plan review for an attending physician to verify.
You have no stake in the outcome. Your job is to ground every clinical claim in
cited guidelines, check all contraindications, stratify patient-specific risk,
and ensure the plan is actionable for direct order entry.

BASE THE REVIEW ON THE INPUT DATA ONLY.

TREATMENT PLAN DATA:
{request_text}

{wiki_context}

Produce a structured treatment-plan review with exactly these sections:

## Guideline review
For every clinical recommendation, cite the specific guideline document and
section number. Do not summarise; quote the operative language if short.
Flag any recommendation that lacks a guideline citation.

## Contraindication check
Check drug-allergy contraindications against patient_summary and
contraindication_context. Check drug-organ-failure contraindications
against lab_values (eGFR, liver enzymes, Child-Pugh if applicable).
Check procedure-comorbidity and procedure-medication contraindications.
Name the mechanism for each finding.

## Risk stratification
Stratify risk using patient-specific factors from patient_summary and
lab_values (age, comorbidities, organ function). Cite numeric thresholds.
Do not import baseline-population risk statistics not grounded in the data.

## Plan revisions
Provide specific dose/route/duration revisions. State exact orders.
If no revision is needed for an element, state "No change required."

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this treatment-plan review. Address EVERY issue in the reviewer's
critique, especially any GUIDELINE FLAGS, CONTRAINDICATION FLAGS, or RISK FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any GUIDELINE FLAG: cite the guideline document and section, not a summary.
⚠️  For any CONTRAINDICATION FLAG: name the specific contraindication mechanism
(drug-allergy, drug-organ, drug-condition).
⚠️  For any RISK FLAG: stratify risk against patient-specific factors
(age, comorbidity, lab values); do not import baseline-population risk.
"""


@dataclass
class TreatmentPlanRequest:
    """Structured input for the treatment-plan review workflow."""

    patient_summary: str
    """De-identified patient summary (age, sex, diagnoses, relevant history)."""

    proposed_plan: str
    """Proposed treatment plan: medications, procedures, interventions."""

    current_medications: str
    """Current medication list from EHR reconciliation."""

    lab_values: str
    """Relevant lab values (eGFR, LFTs, CBC, electrolytes, etc.)."""

    clinical_guidelines: str
    """Applicable clinical guidelines (ACC/AHA, KDIGO, IDSA, etc.) referenced."""

    contraindication_context: str
    """Known allergies, prior adverse drug reactions, organ-function constraints."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Patient summary: {self.patient_summary[:cap]}",
            f"Proposed plan: {self.proposed_plan[:cap]}",
            f"Current medications: {self.current_medications[:cap]}",
            f"Lab values: {self.lab_values[:cap]}",
            f"Clinical guidelines: {self.clinical_guidelines[:cap]}",
            f"Contraindication context: {self.contraindication_context[:cap]}",
        ])


class TreatmentPlanReviewWorkflow(BaseWorkflow):
    """
    Adversarial treatment-plan review: executor grounds the plan in guidelines,
    checks contraindications, and stratifies patient-specific risk → reviewer
    challenges guideline citations, contraindication completeness, and risk
    stratification, with the power to VETO → iterate.

    Convergence gate (D-HEALTH-4):
        score ≥ threshold (8.0)
        AND zero GUIDELINE FLAGS
        AND zero CONTRAINDICATION FLAGS
        AND zero RISK FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: TreatmentPlanRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)

        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None

        current_guideline_flags: list[str] = []
        current_contraindication_flags: list[str] = []
        current_risk_flags: list[str] = []

        all_guideline_flags: list[str] = []
        all_contraindication_flags: list[str] = []
        all_risk_flags: list[str] = []

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
                    current_guideline_flags,
                    current_contraindication_flags,
                    current_risk_flags,
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
                criteria=_TREATMENT_PLAN_REVIEW_CRITERIA,
            )
            score = review.score

            current_guideline_flags = extract_flags(review.critique, "GUIDELINE FLAGS:")
            current_contraindication_flags = extract_flags(
                review.critique, "CONTRAINDICATION FLAGS:"
            )
            current_risk_flags = extract_flags(review.critique, "RISK FLAGS:")

            all_guideline_flags.extend(current_guideline_flags)
            all_contraindication_flags.extend(current_contraindication_flags)
            all_risk_flags.extend(current_risk_flags)

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
                and not current_guideline_flags
                and not current_contraindication_flags
                and not current_risk_flags
            ):
                converged = True
                break

        treatment_checklist = self._build_treatment_checklist(
            {
                "GUIDELINE FLAGS:": all_guideline_flags,
                "CONTRAINDICATION FLAGS:": all_contraindication_flags,
                "RISK FLAGS:": all_risk_flags,
            },
            veto_reason,
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "patient_summary_chars": len(request.patient_summary),
            "guideline_flags": list(dict.fromkeys(all_guideline_flags)),
            "contraindication_flags": list(dict.fromkeys(all_contraindication_flags)),
            "risk_flags": list(dict.fromkeys(all_risk_flags)),
            "treatment_checklist": treatment_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }

        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: preserve clean pre-veto draft for attending physician.
            # L-HEALTH-1: this field may echo sanitized PHI from prompt-supplied
            # caller data (patient_summary, current_medications, lab_values).
            # Callers must apply downstream PHI handling before logging.
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
        guideline_flags: list[str],
        contraindication_flags: list[str],
        risk_flags: list[str],
    ) -> str:
        if not guideline_flags and not contraindication_flags and not risk_flags:
            return ""
        parts: list[str] = []
        if guideline_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(guideline_flags)
            )
            parts.append(
                "⚠️  GUIDELINE FLAGS (ground every clinical claim in the cited "
                "guideline; cite section, not summary):\n"
                f"{flags_text}"
            )
        if contraindication_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(contraindication_flags)
            )
            parts.append(
                "⚠️  CONTRAINDICATION FLAGS (name the specific contraindication "
                "mechanism (drug-allergy, drug-organ, drug-condition)):\n"
                f"{flags_text}"
            )
        if risk_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(risk_flags)
            )
            parts.append(
                "⚠️  RISK FLAGS (stratify risk against patient-specific factors "
                "(age, comorbidity, lab values); do not import baseline-population "
                "risk):\n"
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
    def _build_treatment_checklist(
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Attending Physician]"]

        if veto_reason is not None:
            checklist.append(
                "[ ] \U0001f6d1 REVIEWER VETO — escalate to attending physician "
                "BEFORE any prescribing action"
            )

        guideline_flags = accumulated.get("GUIDELINE FLAGS:", [])
        contraindication_flags = accumulated.get("CONTRAINDICATION FLAGS:", [])
        risk_flags = accumulated.get("RISK FLAGS:", [])

        if guideline_flags:
            checklist.append(
                f"[ ] ⚠️  GUIDELINE FLAGS ({len(guideline_flags)}) — "
                "verify guideline citations resolve to current effective-date version"
            )
        if contraindication_flags:
            checklist.append(
                f"[ ] ⚠️  CONTRAINDICATION FLAGS ({len(contraindication_flags)}) — "
                "name the specific contraindication mechanism (drug-allergy, drug-organ, "
                "drug-condition)"
            )
        if risk_flags:
            checklist.append(
                f"[ ] ⚠️  RISK FLAGS ({len(risk_flags)}) — "
                "stratify risk against patient-specific factors (age, comorbidity, lab values)"
            )

        checklist.extend([
            "[ ] Verify guideline citations resolve to current effective-date version",
            "[ ] Confirm medication reconciliation against EHR med list",
            "[ ] Pharmacy independent verification for new medication orders",
            "[ ] Document risk discussion with patient in EHR",
            "[ ] Order entry only after attending physician sign-off",
        ])

        return checklist
