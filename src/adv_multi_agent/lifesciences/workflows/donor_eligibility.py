"""
Workflow — Donor-Eligibility Determination Review (Lifesciences · Advanced
Therapies / CGT, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to the 21 CFR 1271
Subpart C donor-eligibility determination for an allogeneic cell or tissue
product: executor determines the donor eligible; reviewer (cross-model per ARIS
§2.1) challenges incomplete risk-factor screening, missing / misread
communicable-disease testing, and an "eligible" call inconsistent with the
screening and testing evidence, with the power to VETO when releasing an
allogeneic product from an ineligible or inadequately screened / tested donor.

Boundary (D-LIFESCI-2): distinct from healthcare AdverseEventTriageWorkflow, which
grades clinical severity / causality for a provider. This is the manufacturer's
regulatory eligibility determination under 21 CFR 1271 Subpart C.

Veto gate (D-LIFESCI-6): fires when releasing an allogeneic product from an
ineligible or inadequately screened / tested donor — a communicable-disease
transmission risk.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Donor-screening / eligibility record system — screening should resolve
       against the controlled eligibility record system, not caller-pasted text.
    2. Infectious-disease-testing LIMS — communicable-disease testing should read
       controlled LIMS results with methods and dates.
    3. Deviation / urgent-medical-need documentation — any urgent-medical-need
       path should reconcile against the controlled deviation documentation.
    4. 21 CFR 1271 Subpart C determination log — the determination must map into
       the controlled eligibility log before any release.
    5. Qualified approver gate — every AI-suggested eligibility conclusion must be
       confirmed by a qualified Quality Assurance / Tissue-safety officer. Output
       is never a release of record.
    6. Dedicated third-model eligibility auditor — production should use a
       separately configured auditor model for eligibility-inflation bias
       detection. See ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated donor-eligibility determination review is "
    "decision-support, not a release of record and not a regulatory determination. "
    "A qualified Quality Assurance / Tissue-safety officer must independently "
    "confirm the 21 CFR 1271 Subpart C screening and testing before any release. "
    "Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found the "
    "donor ineligible or inadequately screened / tested; releasing the allogeneic "
    "product risks communicable-disease transmission. See metadata['veto_reason']. "
    "Escalate to Quality Assurance / Tissue-safety; do not release."
)

_FLAG_HEADERS = ("SCREENING-GAP FLAGS:", "TESTING-GAP FLAGS:", "INELIGIBLE-RELEASE FLAGS:")

_DONOR_REVIEW_CRITERIA = """\
Evaluate this donor-eligibility determination review on five dimensions. Score each 0–10.

1. DONOR SCREENING (30%) — CRITICAL
   Is the required risk-factor screening (history, physical assessment, records
   review) complete and correctly interpreted? Penalise incomplete or misread
   screening. Flag under SCREENING-GAP FLAGS:.

2. COMMUNICABLE-DISEASE TESTING (25%) — CRITICAL
   Is the required communicable-disease testing present, by the right method, and
   correctly read (with plasma-dilution addressed)? Penalise missing / wrong /
   misread testing. Flag under TESTING-GAP FLAGS:.

3. ELIGIBILITY DETERMINATION (20%) — CRITICAL
   Is the "eligible" call consistent with the screening and testing evidence, and
   is any urgent-medical-need path documented as such rather than as routine
   eligibility? Penalise an eligible call the evidence does not support. Flag
   under INELIGIBLE-RELEASE FLAGS:.

4. PLASMA-DILUTION & URGENT-NEED DOCUMENTATION (15%)
   Are plasma dilution and any urgent-medical-need path assessed and documented?
   Penalise unaddressed dilution or undocumented urgent-need use.

5. ACTIONABILITY (10%)
   Is each finding specific enough for QA to resolve (which screen, which test,
   which agent)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if releasing the allogeneic product would use an ineligible or
inadequately screened / tested donor — a communicable-disease transmission risk.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SCREENING-GAP FLAGS AND zero TESTING-GAP FLAGS AND zero
INELIGIBLE-RELEASE FLAGS AND no VETO: ready for QA / Tissue-safety sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SCREENING-GAP FLAGS: [bullet list, or "None detected"]
  TESTING-GAP FLAGS: [bullet list, or "None detected"]
  INELIGIBLE-RELEASE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are reviewing a 21 CFR 1271 Subpart C donor-eligibility determination for an
allogeneic cell or tissue product for a qualified Quality Assurance / Tissue-safety
officer. You have no stake in the outcome. Assess whether the screening and
communicable-disease testing support an eligible determination, grounded only in
the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

DONOR-ELIGIBILITY DATA:
{request_text}

{wiki_context}

Produce a structured review with exactly these sections:

## Donor screening
State whether the risk-factor screening (history, physical, records) is complete
and correctly interpreted; identify any gap.

## Communicable-disease testing
State whether the required testing is present, by the right method, and correctly
read (with plasma dilution addressed); identify any gap.

## Eligibility determination
State whether the "eligible" call is consistent with the screening and testing;
identify any unsupported eligible call.

## Plasma dilution and urgent-need documentation
State whether plasma dilution and any urgent-medical-need path are assessed and
documented.

## Eligibility conclusion
State whether the donor is eligible on the supplied evidence, or whether the
determination is unsupported.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this donor-eligibility determination review. Address EVERY issue in the
reviewer's critique, especially any SCREENING-GAP FLAGS, TESTING-GAP FLAGS, or
INELIGIBLE-RELEASE FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SCREENING-GAP flag: complete the required screening element, or
acknowledge the donor cannot be determined eligible.
⚠️  For any TESTING-GAP flag: cite the required communicable-disease test result
(right method, plasma dilution addressed), or acknowledge the gap.
⚠️  For any INELIGIBLE-RELEASE flag: reconcile the eligible call with the evidence,
or acknowledge the donor is ineligible.
"""


@dataclass
class DonorEligibilityRequest:
    """Structured input for the donor-eligibility determination review workflow."""

    donation_type: str
    """Donation type: living / cadaveric; allogeneic."""

    donor_screening_summary: str
    """Risk-factor screening summary (history)."""

    donor_testing_summary: str
    """Communicable-disease testing summary and results."""

    agents_considered: str
    """Relevant communicable-disease agents considered."""

    plasma_dilution_assessment: str
    """Plasma-dilution assessment for the testing sample."""

    physical_assessment_or_records_review: str
    """Physical assessment and/or records review."""

    retesting_or_repeat_status: str
    """Retesting / repeat-donor status where applicable."""

    urgent_medical_need_flag: str
    """Whether an urgent-medical-need path is invoked and how it is documented."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Donation type: {self.donation_type[:cap]}",
            f"Donor screening summary: {self.donor_screening_summary[:cap]}",
            f"Donor testing summary: {self.donor_testing_summary[:cap]}",
            f"Agents considered: {self.agents_considered[:cap]}",
            f"Plasma-dilution assessment: {self.plasma_dilution_assessment[:cap]}",
            f"Physical assessment / records review: {self.physical_assessment_or_records_review[:cap]}",
            f"Retesting / repeat status: {self.retesting_or_repeat_status[:cap]}",
            f"Urgent-medical-need flag: {self.urgent_medical_need_flag[:cap]}",
        ])


class DonorEligibilityWorkflow(BaseWorkflow):
    """
    Adversarial donor-eligibility determination review: executor determines the
    donor eligible → reviewer challenges incomplete screening, missing testing, and
    an unsupported eligible call, with the power to VETO → iterate.

    Convergence gate (D-LIFESCI-6):
        score ≥ threshold (8.0)
        AND zero SCREENING-GAP FLAGS
        AND zero TESTING-GAP FLAGS
        AND zero INELIGIBLE-RELEASE FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the wiki.
    The verbatim veto directive is recorded in metadata['veto_reason'];
    metadata['first_draft'] captures the clean executor draft from the vetoed round.
    """

    async def run(  # type: ignore[override]
        self,
        request: DonorEligibilityRequest,
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
                criteria=_DONOR_REVIEW_CRITERIA,
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

        donor_checklist = self._build_donor_checklist(request, accumulated, veto_reason)

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "donation_type": sanitize_for_prompt(request.donation_type, max_chars=200),
            "screening_gap_flags": list(dict.fromkeys(accumulated["SCREENING-GAP FLAGS:"])),
            "testing_gap_flags": list(dict.fromkeys(accumulated["TESTING-GAP FLAGS:"])),
            "ineligible_release_flags": list(
                dict.fromkeys(accumulated["INELIGIBLE-RELEASE FLAGS:"])
            ),
            "donor_checklist": donor_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-HEALTH-1: this field may echo sanitized caller data
            # (donor_screening_summary, donor_testing_summary) that can carry
            # individually identifiable donor PHI. Callers must apply downstream
            # PHI handling before logging or sharing.
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
        """Thin delegate to `core._internal.extract_veto_directive` (M-PC-1)."""
        return extract_veto_directive(critique, "REVIEWER VETO:", max_chars)

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "SCREENING-GAP FLAGS:": (
                "⚠️  SCREENING-GAP FLAGS (complete the required screening element, or "
                "acknowledge the donor cannot be determined eligible):"
            ),
            "TESTING-GAP FLAGS:": (
                "⚠️  TESTING-GAP FLAGS (cite the required communicable-disease test "
                "result with the right method and plasma dilution, or acknowledge the gap):"
            ),
            "INELIGIBLE-RELEASE FLAGS:": (
                "⚠️  INELIGIBLE-RELEASE FLAGS (reconcile the eligible call with the "
                "evidence, or acknowledge the donor is ineligible):"
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
    def _build_donor_checklist(
        request: DonorEligibilityRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Quality Assurance / Tissue-Safety (Donor-Eligibility) Officer]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — do not release the allogeneic product; escalate "
                "to Quality Assurance / Tissue-safety and complete screening / testing "
                "before any release"
            )
        screening_flags = accumulated.get("SCREENING-GAP FLAGS:", [])
        testing_flags = accumulated.get("TESTING-GAP FLAGS:", [])
        release_flags = accumulated.get("INELIGIBLE-RELEASE FLAGS:", [])
        if screening_flags:
            checklist.append(
                f"[ ] ⚠️  SCREENING-GAP FLAGS ({len(screening_flags)}) — complete each "
                "flagged risk-factor screening element"
            )
        if testing_flags:
            checklist.append(
                f"[ ] ⚠️  TESTING-GAP FLAGS ({len(testing_flags)}) — obtain the "
                "communicable-disease testing for each flagged gap"
            )
        if release_flags:
            checklist.append(
                f"[ ] ⚠️  INELIGIBLE-RELEASE FLAGS ({len(release_flags)}) — reconcile "
                "the eligible call with the evidence before any release"
            )
        checklist.extend([
            "[ ] Confirm risk-factor screening is complete and correctly interpreted",
            "[ ] Confirm communicable-disease testing is present, correct method, correctly read",
            "[ ] Confirm any urgent-medical-need path is documented as such, not routine eligibility",
            "[ ] Obtain Quality Assurance / Tissue-safety sign-off before any release",
        ])
        return checklist
