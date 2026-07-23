"""
Workflow — Clinical Trial Eligibility (Healthcare Teaching Example — Veto + Bias-Gate)
Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to clinical-trial
eligibility determination: executor checks protocol fidelity, grounds biomarker
and prior-treatment evidence, verifies safety exclusion criteria; reviewer
(cross-model per ARIS §2.1) challenges eligibility claims against the protocol,
runs a dedicated BIAS DETECTION dimension (parole-pattern applied to clinical
research per JAMA 2019), and holds veto power on life-safety exclusion or
protected-class bias signals.

Veto gate (D-HEALTH-4): fires on
  • Patient meets a life-threatening safety exclusion criterion but is marked
    eligible (ICH-GCP serious deviation).
  • Protected-class attribute (race, ethnicity, sex, age, disability) is a
    determinative exclusion factor without protocol-specified clinical
    justification (JAMA 2019 cardiology RCT under-representation; analogous
    oncology/neurology literature).
  • Eligibility determination contradicts primary evidence in protocol_summary
    or biomarker_status.

Escalation on veto goes to Principal Investigator + IRB Coordinator.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PHI de-identification — caller's responsibility (HIPAA Safe Harbor /
       Expert Determination) before passing patient_profile and other fields.
    2. Live protocol database — ClinicalTrials.gov API or sponsor EDC
       integration for authoritative protocol text and version control.
    3. Real-time eligibility check — EHR pull at eligibility-check time for
       current labs, medications, and diagnoses.
    4. IRB sign-off gate — enrollment decision is IRB-governed; AI output is
       advisory only. No auto-enrollment.
    5. Dedicated third-model bias auditor — parole-pattern parallel; production
       should run a separately configured auditor model whose only job is
       demographic-bias detection against site enrollment statistics.
    6. Site enrollment statistics — under-representation analysis requires
       site-level demographic data not present in this workflow.
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
    "ADVISORY ONLY — This AI-generated trial-eligibility assessment is not an "
    "enrollment decision. The principal investigator must independently verify every "
    "exclusion criterion against the protocol and the patient's full EHR before "
    "enrollment. The IRB coordinator must confirm bias detection findings against site "
    "enrollment statistics. AI output must never auto-enroll or auto-exclude."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted. The reviewer identified a life-safety "
    "eligibility issue OR a protected-class bias signal. See metadata['veto_reason']. "
    "Escalate to PI and IRB coordinator."
)

_FLAG_HEADERS = ("BIAS FLAGS:", "ELIGIBILITY FLAGS:", "EVIDENCE FLAGS:")

_TRIAL_ELIGIBILITY_REVIEW_CRITERIA = """\
Evaluate this clinical-trial eligibility assessment on five dimensions. Score each 0–10.

1. PROTOCOL FIDELITY (30%) — CRITICAL
   Every eligibility statement must map to a protocol section number. Do not
   paraphrase; cite the protocol section directly. Penalise any eligibility
   claim that lacks a protocol-section reference.
   Flag gaps under ELIGIBILITY FLAGS:.

2. BIAS DETECTION (25%) — CRITICAL
   Scrutinise whether any protected-class attribute — race, ethnicity, sex,
   age (beyond age-range inclusion criteria with clinical justification),
   disability — is used as a determinative factor in eligibility without
   explicit protocol-specified clinical justification.
   Cite the JAMA 2019 systematic review documenting under-representation of
   racial/ethnic minorities and women in cardiology RCTs (Duma et al., JAMA
   Cardiol. 2019;4(3):211-219; analogous patterns documented in oncology and
   neurology RCTs). Any eligibility reasoning that echoes historical
   under-representation patterns must be flagged — the reviewer must veto
   rather than approve bias-driven exclusion.
   Flag gaps under BIAS FLAGS:.

3. EVIDENCE GROUNDING (20%) — CRITICAL
   biomarker_status, lab values, and prior_treatments must be cited directly
   from the input fields, not inferred from free-text summaries or outside
   knowledge. Do not import data not present in the request.
   Flag gaps under EVIDENCE FLAGS:.

4. SAFETY EXCLUSION COMPLETENESS (15%)
   Life-threatening exclusion criteria — organ dysfunction per protocol
   thresholds (eGFR, LVEF, bilirubin, creatinine), prohibited concomitant
   medications, active infection per protocol — must be verified explicitly
   against the protocol and biomarker_status. Penalise assessments that assert
   "no exclusions" without checking each life-threatening exclusion class.
   Flag life-threatening gaps under ELIGIBILITY FLAGS:.

5. DECISION CLARITY (10%)
   The final determination must be one of: eligible / ineligible / requires
   review. The rationale must be traceable to a protocol section number.
   Ambiguous determinations must be flagged.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Patient meets a life-threatening exclusion criterion (organ dysfunction
    per protocol thresholds, prohibited concomitant medication, active
    infection per protocol) but the draft marks patient eligible. Per
    ICH-GCP and IRB protocol governance, enrolling a patient meeting
    safety exclusion is a serious deviation.
  • Protected-class attribute (race, ethnicity, sex, age, disability)
    appears to be a determinative exclusion factor without protocol-
    specified clinical justification. Cf. JAMA 2019 systematic review on
    cardiology RCT under-representation (Duma et al., JAMA Cardiol.
    2019;4(3):211-219); similar patterns documented in oncology / neurology.
    The reviewer must veto rather than approve bias-driven exclusion.
  • Eligibility determination contradicts primary evidence in
    protocol_summary or biomarker_status (e.g. patient marked eligible
    despite biomarker-status mismatch with inclusion criteria).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those
  as stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero BIAS FLAGS AND zero ELIGIBILITY FLAGS AND zero
EVIDENCE FLAGS AND no VETO: assessment is ready for PI and IRB sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  BIAS FLAGS: [bullet list, or "None detected"]
  ELIGIBILITY FLAGS: [bullet list, or "None detected"]
  EVIDENCE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are conducting a clinical-trial eligibility assessment for a principal
investigator to verify before any enrollment decision. You have no stake in
the outcome. Your job is to verify every eligibility criterion against the
protocol, ground biomarker and treatment-history evidence in the input data,
and detect any protected-class bias signal in the reasoning.

BASE THE ASSESSMENT ON THE INPUT DATA ONLY.

TRIAL ELIGIBILITY DATA:
{request_text}

{wiki_context}

Produce a structured eligibility assessment with exactly these sections:

## Protocol fidelity check
For every eligibility statement, cite the specific protocol section number.
Do not paraphrase eligibility criteria — quote the operative criterion language.
Flag any eligibility claim that lacks a protocol-section citation.

## Bias detection
Examine whether race, ethnicity, sex, age (beyond protocol age-range with
clinical justification), or disability is used as a determinative factor.
Cite the JAMA 2019 systematic review on under-representation of minorities
and women in cardiology RCTs when relevant. Document the reasoning explicitly.

## Evidence grounding
For every biomarker, lab value, or treatment-history claim, cite the input
field (biomarker_status, prior_treatments, patient_profile) directly.
Do not infer data not present in the inputs.

## Safety exclusion verification
Verify each life-threatening exclusion criterion class against the protocol:
organ dysfunction thresholds (eGFR, LVEF, bilirubin), prohibited concomitant
medications, active infection criteria. Name the mechanism for each finding.

## Eligibility determination
State: eligible / ineligible / requires review.
Provide a rationale traceable to protocol section numbers.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this clinical-trial eligibility assessment. Address EVERY issue in
the reviewer's critique, especially any BIAS FLAGS, ELIGIBILITY FLAGS, or
EVIDENCE FLAGS.

PREVIOUS ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any BIAS FLAG: document protocol-specified clinical justification for
any use of a protected-class attribute; if none exists, remove it from the
determinative reasoning and flag for IRB review.
⚠️  For any ELIGIBILITY FLAG: cite the protocol section number; do not
paraphrase eligibility criteria.
⚠️  For any EVIDENCE FLAG: cite the biomarker / lab / treatment-history input
directly; do not infer data not present in the inputs.
"""


@dataclass
class TrialEligibilityRequest:
    """Structured input for the clinical-trial eligibility workflow."""

    trial_id: str
    """Trial identifier (e.g. NCT number or sponsor protocol ID)."""

    protocol_summary: str
    """Summary of inclusion and exclusion criteria with section numbers."""

    patient_profile: str
    """De-identified patient profile (age, sex, diagnoses, relevant history)."""

    biomarker_status: str
    """Biomarker and lab results relevant to the trial's inclusion criteria."""

    prior_treatments: str
    """Prior treatment history relevant to eligibility (washout periods, etc.)."""

    competing_risks: str
    """Competing risks, comorbidities, or organ-dysfunction factors."""

    site_context: str
    """Site enrollment context (demographic data, under-representation notes)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Trial ID: {self.trial_id[:cap]}",
            f"Protocol summary: {self.protocol_summary[:cap]}",
            f"Patient profile: {self.patient_profile[:cap]}",
            f"Biomarker status: {self.biomarker_status[:cap]}",
            f"Prior treatments: {self.prior_treatments[:cap]}",
            f"Competing risks: {self.competing_risks[:cap]}",
            f"Site context: {self.site_context[:cap]}",
        ])


class ClinicalTrialEligibilityWorkflow(BaseWorkflow):
    """
    Adversarial clinical-trial eligibility assessment: executor verifies
    protocol fidelity, grounds evidence in input data, checks safety
    exclusions, and detects protected-class bias → reviewer challenges
    every eligibility claim, runs a dedicated BIAS DETECTION dimension
    (parole-pattern applied to clinical research, citing JAMA 2019), and
    holds veto power on safety exclusion violation or bias signal → iterate.

    Convergence gate (D-HEALTH-4):
        score >= threshold (8.0)
        AND zero BIAS FLAGS
        AND zero ELIGIBILITY FLAGS
        AND zero EVIDENCE FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2). Escalation goes to PI and IRB coordinator.
    """

    async def run(  # type: ignore[override]
        self,
        request: TrialEligibilityRequest,
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
                criteria=_TRIAL_ELIGIBILITY_REVIEW_CRITERIA,
            )
            score = review.score

            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

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

        trial_checklist = self._build_trial_checklist(accumulated, veto_reason)

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "trial_id": sanitize_for_prompt(request.trial_id, max_chars=200),
            "bias_flags": list(dict.fromkeys(accumulated["BIAS FLAGS:"])),
            "eligibility_flags": list(dict.fromkeys(accumulated["ELIGIBILITY FLAGS:"])),
            "evidence_flags": list(dict.fromkeys(accumulated["EVIDENCE FLAGS:"])),
            "trial_checklist": trial_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }

        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: preserve clean pre-veto draft for IRB/PI review.
            # L-HEALTH-1: this field may echo sanitized PHI from prompt-supplied
            # caller data (patient_profile, biomarker_status). Callers must
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
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "BIAS FLAGS:": (
                "⚠️  BIAS FLAGS (remove protected-class attribute from "
                "determinative role; document protocol-specified clinical justification "
                "or escalate to IRB):"
            ),
            "ELIGIBILITY FLAGS:": (
                "⚠️  ELIGIBILITY FLAGS (re-verify every criterion against "
                "the protocol section number; do not paraphrase eligibility):"
            ),
            "EVIDENCE FLAGS:": (
                "⚠️  EVIDENCE FLAGS (cite the biomarker / lab / treatment-history "
                "input directly; do not paraphrase eligibility from inferred data):"
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
    def _build_trial_checklist(
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: IRB Coordinator / Principal Investigator]"]

        if veto_reason is not None:
            checklist.append(
                "[ ] \U0001f6d1 REVIEWER VETO — escalate to PI + IRB coordinator "
                "BEFORE any enrollment action"
            )

        bias_flags = accumulated.get("BIAS FLAGS:", [])
        eligibility_flags = accumulated.get("ELIGIBILITY FLAGS:", [])
        evidence_flags = accumulated.get("EVIDENCE FLAGS:", [])

        if bias_flags:
            checklist.append(
                f"[ ] ⚠️  BIAS FLAGS ({len(bias_flags)}) — "
                "document protocol-specified clinical justification for any use of a "
                "protected-class attribute; if none, remove from determinative reasoning"
            )
        if eligibility_flags:
            checklist.append(
                f"[ ] ⚠️  ELIGIBILITY FLAGS ({len(eligibility_flags)}) — "
                "re-verify every criterion against the protocol section number"
            )
        if evidence_flags:
            checklist.append(
                f"[ ] ⚠️  EVIDENCE FLAGS ({len(evidence_flags)}) — "
                "confirm biomarker status from primary lab report, not free-text summary"
            )

        checklist.extend([
            "[ ] Verify every exclusion criterion against protocol section number",
            "[ ] Confirm biomarker status from primary lab report, not free-text summary",
            (
                "[ ] If BIAS FLAGS present, document protocol-specified clinical "
                "justification AND review site enrollment statistics for under-representation"
            ),
            "[ ] IRB and PI joint sign-off before enrollment",
            "[ ] Document eligibility decision rationale in regulatory binder per ICH-GCP",
        ])

        return checklist
