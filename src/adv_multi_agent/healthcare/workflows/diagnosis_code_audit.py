"""
Workflow — Diagnosis Code Audit (Healthcare Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for ICD-10-CM/PCS and
CPT coding accuracy. Executor proposes/audits codes; reviewer (recommended:
different model family) challenges accuracy, compliance with payer guidelines,
and specificity (avoiding upcoding and undercoding).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PHI de-identification — encounter_summary is free-text; caller's
       responsibility to ensure HIPAA Safe Harbor / Expert Determination
       de-identification before submission.
    2. EHR integration — clinical documentation should be pulled from
       Epic/Cerner, not manually excerpted.
    3. Live coding reference — ICD-10-CM/PCS Official Guidelines, AHA Coding
       Clinic, and CPT Assistant should be integrated as authoritative
       references, not caller-supplied text.
    4. Certified coder review gate — all AI-suggested code changes must be
       reviewed and confirmed by a credentialed coder (CCS, CPC) before
       claim submission.
    5. RAC / OIG audit trail — any code changes must be documented with
       rationale for compliance audit purposes.
    6. Dedicated third-model coding auditor — production should use a
       separately configured auditor model for specificity bias detection.
       See ARIS §3.1.
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

# L-PC-3: per-field cap — prevents a single oversized field crowding out
# later fields when the concatenated prompt is trimmed by sanitize_for_prompt.
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated coding audit is not a billing "
    "submission. A credentialed coder (CCS, CPC) must independently verify "
    "every code change against primary documentation before any claim is "
    "submitted. AI output must never trigger automated billing."
)

_DIAGNOSIS_REVIEW_CRITERIA = """\
Evaluate this diagnosis-code audit on five dimensions. Score each 0–10.

1. CODE-TO-DOCUMENTATION ACCURACY (30%)
   Does every proposed code map to specific language in the encounter
   documentation? Are codes neither upcoded (unsupported severity/specificity)
   nor undercoded (under-documenting captured conditions)? Flag mismatches
   under ACCURACY FLAGS:.

2. GUIDELINE COMPLIANCE (25%)
   Are proposed codes consistent with ICD-10-CM Official Guidelines, AHA
   Coding Clinic, payer LCD/NCD, and CPT coding conventions? Flag deviations
   under COMPLIANCE FLAGS:.

3. SPECIFICITY (20%)
   Is the most specific code available used, or has a less-specific code
   been chosen where documentation supports specificity (e.g. CKD stage,
   diabetes complication, fracture laterality)? Flag specificity gaps under
   SPECIFICITY FLAGS:.

4. PAYER-SPECIFIC FIT (15%)
   Does the code set align with the payer's policy and DRG/APC assignment
   expectations? Penalise advice that ignores payer_guidelines.

5. ACTIONABILITY (10%)
   Are recommended changes specific enough for the coder to apply (code,
   replacement, evidence citation)?

Overall score = weighted average.
Score ≥ 7.5 AND zero ACCURACY FLAGS AND zero COMPLIANCE FLAGS AND zero
SPECIFICITY FLAGS: ready for coder review.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  ACCURACY FLAGS: [bullet list, or "None detected"]
  COMPLIANCE FLAGS: [bullet list, or "None detected"]
  SPECIFICITY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are auditing diagnosis and procedure codes for a credentialed coder to
review. You have no stake in the outcome. Audit codes against the encounter
documentation — not against general coding norms.

BASE EVERY RECOMMENDATION ON THE INPUT DOCUMENTATION. Do not import
assumptions from other cases not present in the encounter summary, codes,
or payer guidelines below.

ENCOUNTER (caller-supplied — verify against EHR before acting):
{request_text}

{wiki_context}

Produce an audit with:

## Code accuracy
- Code-by-code mapping to documentation language

## Compliance check
- ICD-10-CM Official Guidelines / AHA Coding Clinic / payer LCD references

## Specificity gaps
- Less-specific codes where documentation supports specificity

## Recommended changes
- Code | Current | Recommended | Evidence citation

## Claims
- Specific factual claims about the documentation that ground the audit
"""

_REVISION_PROMPT = """\
Revise the diagnosis-code audit based on reviewer critique.

ORIGINAL AUDIT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: REMOVE the unsupported code claim or replace it
with documentation evidence from the encounter summary. Do not rephrase.
"""


@dataclass
class DiagnosisCodeAuditRequest:
    """Structured input for the diagnosis-code audit workflow."""

    encounter_summary: str
    """Clinical documentation excerpt (H&P, discharge summary, op note)."""

    proposed_codes: str
    """ICD-10-CM/PCS or CPT codes with descriptions proposed by coder."""

    provider_specialty: str
    """Specialty context for coding conventions."""

    payer_guidelines: str
    """Payer-specific coding guidelines or LCD/NCD references."""

    previous_audits: str
    """Prior coding audit findings for this provider or encounter type."""

    clinical_context: str
    """Admission type (IP/OP/ED), procedure details, LOS."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Encounter summary: {self.encounter_summary[:cap]}",
            f"Proposed codes: {self.proposed_codes[:cap]}",
            f"Provider specialty: {self.provider_specialty[:cap]}",
            f"Payer guidelines: {self.payer_guidelines[:cap]}",
            f"Previous audits: {self.previous_audits[:cap]}",
            f"Clinical context: {self.clinical_context[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "ACCURACY FLAGS:",
    "COMPLIANCE FLAGS:",
    "SPECIFICITY FLAGS:",
)


class DiagnosisCodeAuditWorkflow(BaseWorkflow):
    """
    Adversarial diagnosis-code audit: executor proposes/audits codes →
    reviewer challenges accuracy, compliance, and specificity → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero ACCURACY FLAGS
        AND zero COMPLIANCE FLAGS
        AND zero SPECIFICITY FLAGS

    No reviewer veto — coding corrections are reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: DiagnosisCodeAuditRequest,
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
                criteria=_DIAGNOSIS_REVIEW_CRITERIA,
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

            if review.approved and not self._flag_classes_unresolved(
                review.critique, _FLAG_HEADERS, current.values()
            ):
                converged = True
                break

        audit_checklist = self._build_audit_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "provider_specialty": sanitize_for_prompt(
                    request.provider_specialty, max_chars=200
                ),
                "accuracy_flags": list(dict.fromkeys(accumulated["ACCURACY FLAGS:"])),
                "compliance_flags": list(dict.fromkeys(accumulated["COMPLIANCE FLAGS:"])),
                "specificity_flags": list(dict.fromkeys(accumulated["SPECIFICITY FLAGS:"])),
                "audit_checklist": audit_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "ACCURACY FLAGS:": (
                "⚠️  ACCURACY FLAGS (correct the code-to-documentation mismatch; "
                "do not infer codes beyond what the encounter supports):"
            ),
            "COMPLIANCE FLAGS:": (
                "⚠️  COMPLIANCE FLAGS (align with ICD-10-CM Official Guidelines / "
                "AHA Coding Clinic / payer LCD; cite the specific guidance):"
            ),
            "SPECIFICITY FLAGS:": (
                "⚠️  SPECIFICITY FLAGS (use the most specific code the documentation "
                "supports; do not default to unspecified codes):"
            ),
        }
        parts: list[str] = []
        for header in _FLAG_HEADERS:
            items = current[header]
            if not items:
                continue
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(items)
            )
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _build_audit_checklist(
        request: DiagnosisCodeAuditRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Health Information Manager / Certified Coder (CCS/CPC)]")
        if accumulated["ACCURACY FLAGS:"]:
            checklist.append(
                "[ ] Verify every flagged code change against primary encounter "
                "documentation before claim submission"
            )
        if accumulated["COMPLIANCE FLAGS:"]:
            checklist.append(
                "[ ] Confirm cited ICD-10-CM / AHA Coding Clinic / payer LCD "
                "references resolve to current effective-date guidance"
            )
        if accumulated["SPECIFICITY FLAGS:"]:
            checklist.append(
                "[ ] Resolve specificity gaps by querying the provider for "
                "additional documentation, not by guessing"
            )
        checklist.append(
            "[ ] Document audit rationale in the coding compliance log "
            "(RAC / OIG audit trail)"
        )
        checklist.append(
            "[ ] Submit claim only after credentialed coder sign-off"
        )
        return checklist
