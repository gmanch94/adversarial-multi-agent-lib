"""
Workflow — Drug Interaction Flagging (Healthcare Teaching Example — Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to clinical
drug-interaction review: executor flags potential interactions between a
newly-proposed medication and an existing patient medication list; reviewer
(cross-model per ARIS §2.1) challenges severity grading, evidence quality,
and contraindication completeness, with the power to VETO when an absolute
contraindication or patient-safety-critical condition is detected.

Veto gate (D-HEALTH-2): fires on absolute contraindication, QTc-prolonging
combination with cardiac history, narrow-therapeutic-index interaction without
a dose-adjustment plan, or cross-allergy with documented allergy history.

This is the first veto-using workflow in the healthcare domain and serves as
the worked example for the veto pattern. See product_liability_root_cause.py
(industrial) for the original veto reference.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PHI de-identification — caller is responsible for stripping PHI
       before passing patient_id and medication_list to this workflow.
    2. Live interaction database (Lexicomp / Micromedex / First Databank) —
       formulary_reference is caller-supplied text; no live database query
       is performed.
    3. EHR medication reconciliation — medication_list should be pulled from
       a verified EHR source; free-text entry introduces transcription risk.
    4. Pharmacist order verification gate — no flagged interaction may be
       dispensed without independent pharmacist review; this workflow does
       not trigger or replace that gate.
    5. Renal / hepatic dosing calculator — dose adjustments cited here should
       be verified against a validated calculator (Cockcroft-Gault, MDRD,
       Child-Pugh) integrated with the EHR.
    6. Dedicated third-model interaction auditor — see ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated drug-interaction review is not a "
    "pharmacist verification. A licensed clinical pharmacist must independently "
    "verify every flagged interaction against the live formulary / interaction "
    "database (Lexicomp, Micromedex) before any medication is dispensed or "
    "administered. AI output must never trigger automated prescribing or dispensing."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer identified "
    "a drug-interaction condition that requires immediate clinical-pharmacist "
    "escalation BEFORE any prescribing decision. See metadata['veto_reason']. "
    "Escalate to clinical pharmacist."
)

_FLAG_HEADERS = ("SEVERITY FLAGS:", "EVIDENCE FLAGS:", "CONTRAINDICATION FLAGS:")

_DRUG_INTERACTION_REVIEW_CRITERIA = """\
Evaluate this drug-interaction review on five dimensions. Score each 0–10.

1. SEVERITY ASSESSMENT (30%) — CRITICAL
   Is each flagged interaction graded against the formulary reference supplied
   in the case, not against training-data severity assumptions? Are severity
   ratings consistent with the cited monograph or guideline? Penalise severity
   claims not anchored to the supplied formulary_reference. Flag gaps under
   SEVERITY FLAGS:.

2. EVIDENCE-BASE CITATION (25%) — CRITICAL
   Does each interaction claim cite a specific monograph or guideline entry
   (e.g., "Lexicomp: warfarin + NSAID — major")? Penalise paraphrased severity
   without source. Flag gaps under EVIDENCE FLAGS:.

3. CONTRAINDICATION COMPLETENESS (20%) — CRITICAL
   Are drug-drug, drug-condition, AND drug-allergy contraindications checked?
   Is every drug in medication_list checked against new_medication? Flag every
   gap under CONTRAINDICATION FLAGS:.

4. ORGAN-FUNCTION DOSING (15%)
   For the patient's renal_function and hepatic_function values, are dose
   adjustments correctly calculated and grounded in the input values (not
   generic thresholds)? Penalise adjustments that ignore the supplied
   renal_function / hepatic_function data.

5. ACTIONABILITY (10%)
   Is the recommended action specific (hold, adjust dose, swap, monitor with
   specific parameter)? Vague recommendations ("use with caution") should be
   flagged.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Absolute contraindication between new_medication and any drug in
    medication_list per formulary or standard interaction reference.
  • QTc-prolonging combination in patient with documented cardiac history
    or prolonged baseline QTc.
  • Narrow-therapeutic-index interaction (warfarin + NSAID, lithium +
    thiazide, etc.) without a documented dose-adjustment plan.
  • Cross-allergy with a documented allergy in allergy_history.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
"Overall", "Key issues", or a "#" markdown header — the parser uses those
as stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score ≥ 8.0 AND zero SEVERITY FLAGS AND zero EVIDENCE FLAGS AND zero
CONTRAINDICATION FLAGS AND no VETO: review is ready for pharmacist sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SEVERITY FLAGS: [bullet list, or "None detected"]
  EVIDENCE FLAGS: [bullet list, or "None detected"]
  CONTRAINDICATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are conducting a drug-interaction review for a licensed clinical pharmacist
to verify. You have no stake in the outcome. Your job is to flag every
clinically significant interaction between the proposed new medication and the
existing patient medication list, grounded in the formulary reference supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

PATIENT DATA:
{request_text}

{wiki_context}

Produce a structured drug-interaction review with exactly these sections:

## Interaction analysis
For each drug in the existing medication list, assess interaction with the new
medication. State the interaction type, mechanism, and severity per the
formulary reference.

## Severity grading
Grade each interaction (contraindicated / major / moderate / minor) against
the formulary reference. Cite the specific monograph entry.

## Contraindication check
Drug-drug: list all absolute or relative contraindications.
Drug-condition: consider renal_function, hepatic_function, and the patient's
indication in context.
Drug-allergy: cross-check new_medication class against allergy_history.

## Dose-adjustment recommendation
Given renal_function and hepatic_function values, state whether dose adjustment
is required and the specific adjusted regimen. Cite validated calculator basis.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this drug-interaction review. Address EVERY issue in the reviewer's
critique, especially any SEVERITY FLAGS, EVIDENCE FLAGS, or
CONTRAINDICATION FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SEVERITY FLAG: re-grade against the supplied formulary reference;
do not use training-data severity assumptions.
⚠️  For any EVIDENCE FLAG: cite the specific monograph or guideline entry;
do not paraphrase severity.
⚠️  For any CONTRAINDICATION FLAG: name the contraindicating drug pair or
allergy mechanism explicitly.
"""


@dataclass
class DrugInteractionRequest:
    """Structured input for the drug-interaction flagging workflow."""

    patient_id: str
    """De-identified patient identifier."""

    medication_list: str
    """Current medication list (name, dose, frequency) from verified EHR source."""

    new_medication: str
    """Proposed new medication (name, dose, frequency, route)."""

    indication: str
    """Clinical indication for the new medication."""

    renal_function: str
    """Current renal function (eGFR or CrCl + stage)."""

    hepatic_function: str
    """Current hepatic function (LFTs, Child-Pugh score if available)."""

    allergy_history: str
    """Documented drug allergies and reaction types from patient record."""

    formulary_reference: str
    """Relevant formulary or interaction-database extract (Lexicomp, Micromedex)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Patient ID: {self.patient_id[:cap]}",
            f"Medication list: {self.medication_list[:cap]}",
            f"New medication: {self.new_medication[:cap]}",
            f"Indication: {self.indication[:cap]}",
            f"Renal function: {self.renal_function[:cap]}",
            f"Hepatic function: {self.hepatic_function[:cap]}",
            f"Allergy history: {self.allergy_history[:cap]}",
            f"Formulary reference: {self.formulary_reference[:cap]}",
        ])


class DrugInteractionFlaggingWorkflow(BaseWorkflow):
    """
    Adversarial drug-interaction review: executor flags interactions →
    reviewer challenges severity grading, evidence quality, and contraindication
    completeness, with the power to VETO → iterate.

    Convergence gate (D-HEALTH-2):
        score ≥ threshold (8.0)
        AND zero SEVERITY FLAGS
        AND zero EVIDENCE FLAGS
        AND zero CONTRAINDICATION FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: DrugInteractionRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_severity_flags: list[str] = []
        current_evidence_flags: list[str] = []
        current_contraindication_flags: list[str] = []
        all_severity_flags: list[str] = []
        all_evidence_flags: list[str] = []
        all_contraindication_flags: list[str] = []
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
                    current_severity_flags,
                    current_evidence_flags,
                    current_contraindication_flags,
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
                criteria=_DRUG_INTERACTION_REVIEW_CRITERIA,
            )
            score = review.score
            current_severity_flags = extract_flags(review.critique, "SEVERITY FLAGS:")
            current_evidence_flags = extract_flags(review.critique, "EVIDENCE FLAGS:")
            current_contraindication_flags = extract_flags(
                review.critique, "CONTRAINDICATION FLAGS:"
            )
            all_severity_flags.extend(current_severity_flags)
            all_evidence_flags.extend(current_evidence_flags)
            all_contraindication_flags.extend(current_contraindication_flags)

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

            if (
                review.approved
                and not current_severity_flags
                and not current_evidence_flags
                and not current_contraindication_flags
            ):
                converged = True
                break

        interaction_checklist = self._build_interaction_checklist(
            request,
            {
                "SEVERITY FLAGS:": all_severity_flags,
                "EVIDENCE FLAGS:": all_evidence_flags,
                "CONTRAINDICATION FLAGS:": all_contraindication_flags,
            },
            veto_reason,
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "new_medication": sanitize_for_prompt(
                request.new_medication, max_chars=200
            ),
            "severity_flags": list(dict.fromkeys(all_severity_flags)),
            "evidence_flags": list(dict.fromkeys(all_evidence_flags)),
            "contraindication_flags": list(dict.fromkeys(all_contraindication_flags)),
            "interaction_checklist": interaction_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round
            # so the clinical pharmacist sees what the AI produced before the
            # REVIEWER VETO banner was prepended.
            # L-HEALTH-1: this field may echo sanitized PHI from prompt-supplied
            # caller data (medication_list, allergy_history). Callers must
            # apply downstream PHI handling before logging or sharing.
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
        severity_flags: list[str],
        evidence_flags: list[str],
        contraindication_flags: list[str],
    ) -> str:
        if not severity_flags and not evidence_flags and not contraindication_flags:
            return ""
        parts: list[str] = []
        if severity_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(severity_flags)
            )
            parts.append(
                "⚠️  SEVERITY FLAGS (narrow severity to formulary reference; "
                "do not import training-data severity assumptions):\n"
                f"{flags_text}"
            )
        if evidence_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(evidence_flags)
            )
            parts.append(
                "⚠️  EVIDENCE FLAGS (cite the specific monograph or guideline "
                "entry; do not paraphrase severity):\n"
                f"{flags_text}"
            )
        if contraindication_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(contraindication_flags)
            )
            parts.append(
                "⚠️  CONTRAINDICATION FLAGS (name the contraindicating drug pair "
                "or allergy mechanism explicitly):\n"
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
    def _build_interaction_checklist(
        request: DrugInteractionRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Clinical Pharmacist]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — escalate to clinical pharmacist "
                "BEFORE any prescribing action"
            )
        severity_flags = accumulated.get("SEVERITY FLAGS:", [])
        evidence_flags = accumulated.get("EVIDENCE FLAGS:", [])
        contraindication_flags = accumulated.get("CONTRAINDICATION FLAGS:", [])
        if severity_flags:
            checklist.append(
                f"[ ] ⚠️  SEVERITY FLAGS ({len(severity_flags)}) — re-grade "
                "against live formulary reference, not training-data assumption"
            )
        if evidence_flags:
            checklist.append(
                f"[ ] ⚠️  EVIDENCE FLAGS ({len(evidence_flags)}) — cite specific "
                "Lexicomp / Micromedex monograph entry for each flagged interaction"
            )
        if contraindication_flags:
            checklist.append(
                f"[ ] ⚠️  CONTRAINDICATION FLAGS ({len(contraindication_flags)}) — "
                "resolve each drug-drug, drug-condition, and drug-allergy pair"
            )
        checklist.extend([
            "[ ] Verify every flagged interaction against live Lexicomp / Micromedex monograph",
            "[ ] Confirm renal / hepatic dose adjustments against validated calculator "
            "(Cockcroft-Gault, MDRD, Child-Pugh)",
            "[ ] Pharmacist sign-off in EHR before dispensing",
        ])
        return checklist
