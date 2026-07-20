"""
Workflow — Sterility Assurance Review (Lifesciences · Devices, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to sterilization
validation and sterility assurance: executor assesses whether the claimed
sterility assurance level (SAL) is demonstrated by the validation and routine
control data; reviewer (cross-model per ARIS §2.1) challenges an undemonstrated
SAL, out-of-limit bioburden, and a validation gap, with the power to VETO the
release of product as sterile when the SAL is not demonstrated.

Veto gate (D-LIFESCI-4): fires when product is proposed for release as sterile
while the claimed SAL is NOT demonstrated (a validation gap, or bioburden above
the validated limit).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Sterilization-validation records system — validation evidence (half-cycle,
       dose-setting, overkill) should resolve against the controlled validation
       records, not caller-pasted text.
    2. Bioburden / environmental-monitoring LIMS — bioburden and monitoring data
       should resolve against the controlled microbiology LIMS.
    3. Dosimetry / biological-indicator release system — routine release controls
       should resolve against the controlled dosimetry/BI system.
    4. Sterile-barrier packaging-validation records — the barrier system
       validation should resolve against the controlled packaging records.
    5. Qualified approver gate — every AI-suggested sterility conclusion must be
       reviewed by qualified Microbiology Quality. Output is never an auto-certified
       sterility release; no product is released as sterile by this workflow.
    6. Dedicated third-model sterility auditor — production should use a
       separately configured auditor model for SAL bias detection. See ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated sterility assurance review is "
    "decision-support, not a sterility release decision and not a certification. "
    "Qualified Microbiology Quality must independently confirm the SAL "
    "demonstration, bioburden control, and validation completeness before any "
    "product is released as sterile. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found "
    "product proposed for release as sterile while the claimed SAL is not "
    "demonstrated. See metadata['veto_reason']. Escalate to Microbiology Quality; "
    "product must not be released as sterile until the SAL is demonstrated."
)

_FLAG_HEADERS = ("SAL FLAGS:", "BIOBURDEN FLAGS:", "VALIDATION-GAP FLAGS:")

_STERILITY_REVIEW_CRITERIA = """\
Evaluate this sterility assurance review on five dimensions. Score each 0–10.

1. SAL DEMONSTRATION (30%) — CRITICAL
   Is the claimed sterility assurance level demonstrated by the validation and
   routine-control data? Penalise a SAL claim not supported by the data. Flag
   under SAL FLAGS:.

2. BIOBURDEN CONTROL (25%) — CRITICAL
   Is routine bioburden within the validated limit, and is monitoring adequate to
   support the cycle? Penalise bioburden trending above the validated limit or
   inadequate monitoring. Flag under BIOBURDEN FLAGS:.

3. VALIDATION COMPLETENESS (20%) — CRITICAL
   Is every sterilization-validation element and sterile-barrier element present
   and current for the claimed SAL? Penalise a missing or expired validation
   element. Flag under VALIDATION-GAP FLAGS:.

4. ROUTINE-CONTROL / REVALIDATION RIGOR (15%)
   Are routine release controls (biological indicators, dosimetry) and the
   revalidation cadence adequate? Penalise weak routine control.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which control, which limit, which
   validation element)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if product is proposed for release as sterile while the claimed SAL
is not demonstrated (a validation gap, or bioburden above the validated limit).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SAL FLAGS AND zero BIOBURDEN FLAGS AND zero VALIDATION-GAP
FLAGS AND no VETO: ready for Microbiology Quality sign-off. Otherwise: requires
revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SAL FLAGS: [bullet list, or "None detected"]
  BIOBURDEN FLAGS: [bullet list, or "None detected"]
  VALIDATION-GAP FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are producing a sterility assurance review for qualified Microbiology Quality
to approve. You have no stake in the outcome. Assess whether the claimed SAL is
demonstrated, whether bioburden is controlled, and whether the validation is
complete — grounded only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

STERILITY ASSURANCE DATA:
{request_text}

{wiki_context}

Produce a structured review with exactly these sections:

## SAL demonstration
State whether the claimed sterility assurance level is demonstrated by the
validation and routine-control data. Do not assert a SAL the data do not support.

## Bioburden control
State whether routine bioburden is within the validated limit and monitoring is
adequate.

## Validation completeness
State whether every validation and sterile-barrier element is present and current.

## Routine control and disposition
State the routine-control adequacy and whether the product may be released as sterile.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this sterility assurance review. Address EVERY issue in the reviewer's
critique, especially any SAL FLAGS, BIOBURDEN FLAGS, or VALIDATION-GAP FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SAL flag: do not assert a SAL the validation/routine data do not support.
⚠️  For any BIOBURDEN flag: state the bioburden vs the validated limit.
⚠️  For any VALIDATION-GAP flag: name the missing/expired validation element.
"""


@dataclass
class SterilityAssuranceRequest:
    """Structured input for the sterility assurance review workflow."""

    product_description: str
    """Generic sterile-device category and its material/packaging."""

    sterilization_method: str
    """Sterilization method (EO / radiation / steam) and rationale."""

    sal_target: str
    """Claimed sterility assurance level (e.g. 10^-6)."""

    bioburden_summary: str
    """Routine bioburden monitoring data."""

    validation_summary: str
    """Method validation evidence (half-cycle / dose-setting / overkill)."""

    packaging_barrier: str
    """Sterile-barrier system validation."""

    routine_control_summary: str
    """Routine release controls (biological indicators, dosimetry)."""

    revalidation_status: str
    """Revalidation cadence and last result."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Sterilization method: {self.sterilization_method[:cap]}",
            f"SAL target: {self.sal_target[:cap]}",
            f"Bioburden summary: {self.bioburden_summary[:cap]}",
            f"Validation summary: {self.validation_summary[:cap]}",
            f"Packaging barrier: {self.packaging_barrier[:cap]}",
            f"Routine control summary: {self.routine_control_summary[:cap]}",
            f"Revalidation status: {self.revalidation_status[:cap]}",
        ])


class SterilityAssuranceWorkflow(BaseWorkflow):
    """
    Adversarial sterility assurance review: executor assesses SAL demonstration,
    bioburden control, and validation completeness → reviewer challenges an
    undemonstrated SAL, out-of-limit bioburden, and a validation gap, with the
    power to VETO → iterate.

    Convergence gate (D-LIFESCI-4):
        score ≥ threshold (8.0)
        AND zero SAL FLAGS
        AND zero BIOBURDEN FLAGS
        AND zero VALIDATION-GAP FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: SterilityAssuranceRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_sal_flags: list[str] = []
        current_bioburden_flags: list[str] = []
        current_validation_flags: list[str] = []
        all_sal_flags: list[str] = []
        all_bioburden_flags: list[str] = []
        all_validation_flags: list[str] = []
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
                    current_sal_flags,
                    current_bioburden_flags,
                    current_validation_flags,
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
                criteria=_STERILITY_REVIEW_CRITERIA,
            )
            score = review.score
            current_sal_flags = extract_flags(review.critique, "SAL FLAGS:")
            current_bioburden_flags = extract_flags(review.critique, "BIOBURDEN FLAGS:")
            current_validation_flags = extract_flags(
                review.critique, "VALIDATION-GAP FLAGS:"
            )
            all_sal_flags.extend(current_sal_flags)
            all_bioburden_flags.extend(current_bioburden_flags)
            all_validation_flags.extend(current_validation_flags)

            # Audit-trail write happens BEFORE the veto check (D-LIFESCI-4).
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
                and not current_sal_flags
                and not current_bioburden_flags
                and not current_validation_flags
            ):
                converged = True
                break

        sterility_checklist = self._build_sterility_checklist(
            request,
            {
                "SAL FLAGS:": all_sal_flags,
                "BIOBURDEN FLAGS:": all_bioburden_flags,
                "VALIDATION-GAP FLAGS:": all_validation_flags,
            },
            veto_reason,
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "sal_flags": list(dict.fromkeys(all_sal_flags)),
            "bioburden_flags": list(dict.fromkeys(all_bioburden_flags)),
            "validation_gap_flags": list(dict.fromkeys(all_validation_flags)),
            "sterility_checklist": sterility_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the approver sees what the AI produced before the REVIEWER VETO
            # banner was prepended.
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
        sal_flags: list[str],
        bioburden_flags: list[str],
        validation_flags: list[str],
    ) -> str:
        if not sal_flags and not bioburden_flags and not validation_flags:
            return ""
        parts: list[str] = []
        if sal_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(sal_flags)
            )
            parts.append(
                "⚠️  SAL FLAGS (do not assert a SAL the validation/routine data do "
                "not support):\n"
                f"{flags_text}"
            )
        if bioburden_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(bioburden_flags)
            )
            parts.append(
                "⚠️  BIOBURDEN FLAGS (state the bioburden vs the validated limit):\n"
                f"{flags_text}"
            )
        if validation_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(validation_flags)
            )
            parts.append(
                "⚠️  VALIDATION-GAP FLAGS (name the missing/expired validation "
                "element):\n"
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
    def _build_sterility_checklist(
        request: SterilityAssuranceRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Sterilization / Microbiology Quality]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — product is proposed for release as sterile "
                "while the claimed SAL is not demonstrated; escalate to Microbiology "
                "Quality and do not release as sterile until the SAL is demonstrated"
            )
        sal_flags = accumulated.get("SAL FLAGS:", [])
        bioburden_flags = accumulated.get("BIOBURDEN FLAGS:", [])
        validation_flags = accumulated.get("VALIDATION-GAP FLAGS:", [])
        if sal_flags:
            checklist.append(
                f"[ ] ⚠️  SAL FLAGS ({len(sal_flags)}) — demonstrate the claimed SAL "
                "with validation/routine data"
            )
        if bioburden_flags:
            checklist.append(
                f"[ ] ⚠️  BIOBURDEN FLAGS ({len(bioburden_flags)}) — bring bioburden "
                "within the validated limit or requalify the cycle"
            )
        if validation_flags:
            checklist.append(
                f"[ ] ⚠️  VALIDATION-GAP FLAGS ({len(validation_flags)}) — complete "
                "or renew each missing/expired validation element"
            )
        checklist.extend([
            "[ ] Demonstrate the claimed SAL with current validation and routine data",
            "[ ] Confirm routine bioburden is within the validated limit",
            "[ ] Confirm every validation and sterile-barrier element is current",
            "[ ] Obtain Microbiology Quality sign-off before any sterile release",
        ])
        return checklist
