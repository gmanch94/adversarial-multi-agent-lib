"""
Workflow — CMO / CDMO Qualification Review (Lifesciences · Cross-segment)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for contract-manufacturer
qualification. Executor argues a CMO/CDMO is qualified for the intended scope;
reviewer (recommended: different model family) challenges unremediated GMP
deficiencies, data-integrity weaknesses, and inadequate capacity/continuity.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Supplier-qualification / audit system — audit findings and history should
       be read live from the controlled supplier-qualification system, not
       caller-pasted text.
    2. Quality-agreement repository — the quality agreement should resolve
       against the controlled, executed agreement of record.
    3. CAPA-sharing portal — CAPA status should reflect the shared CAPA system,
       not a manual summary.
    4. Supplier scorecard — performance trend should resolve against the
       controlled supplier scorecard.
    5. Qualified approver gate — every AI-suggested finding must be reviewed and
       confirmed by a qualified Supplier Quality / External Manufacturing lead;
       output is never a supplier-approval of record.
    6. Dedicated third-model supplier auditor — production should use a
       separately configured auditor model for GMP-gap bias detection. See
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
    "ADVISORY ONLY — This AI-generated CMO / CDMO qualification review is "
    "decision-support, not a supplier-approval decision and not a regulatory "
    "record. A qualified Supplier Quality / External Manufacturing lead must "
    "independently verify every GMP, data-integrity, and capacity finding "
    "against the controlled qualification system before a supplier is approved. "
    "Not legal or medical advice."
)

_CMO_REVIEW_CRITERIA = """\
Evaluate this CMO / CDMO qualification review on five dimensions. Score each 0–10.

1. GMP COMPLIANCE (30%) — CRITICAL
   Are all GMP deficiencies from audits and inspection history remediated or
   under an adequate, time-bound CAPA? Penalise a GMP deficiency treated as
   closed without remediation. Flag under GMP-GAP FLAGS:.

2. DATA INTEGRITY (25%) — CRITICAL
   Is the CMO's data-integrity posture adequate (audit trails, review, no shared
   logins), with any weakness addressed? Penalise a data-integrity weakness left
   unaddressed. Flag under DATA-INTEGRITY FLAGS:.

3. CAPACITY & CONTINUITY (20%) — CRITICAL
   Is declared capacity (and business-continuity / redundancy) adequate for the
   committed volume and timeline? Penalise a capacity claim the assessment does
   not support. Flag under CAPACITY FLAGS:.

4. QUALITY-AGREEMENT COVERAGE (15%)
   Does an executed quality agreement define responsibilities, change control,
   and CAPA linkage? Penalise gaps in the quality-agreement coverage.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which observation, which system,
   which CAPA)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero GMP-GAP FLAGS AND zero DATA-INTEGRITY FLAGS AND zero
CAPACITY FLAGS: ready for Supplier Quality sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  GMP-GAP FLAGS: [bullet list, or "None detected"]
  DATA-INTEGRITY FLAGS: [bullet list, or "None detected"]
  CAPACITY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are reviewing a CMO / CDMO qualification for a Supplier Quality / External
Manufacturing lead to review. You have no stake in the outcome. Judge whether
the contract manufacturer is qualified for the intended scope against the
supplied evidence — not against general supplier norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert an audit finding, CAPA,
or capacity fact that is not present in the material below.

SUPPLIER-QUALIFICATION EXCERPT (caller-supplied — verify against the controlled
qualification system before acting):
{request_text}

{wiki_context}

Produce a review with:

## GMP compliance
- Whether audit findings and inspection history are remediated or under CAPA

## Data integrity
- Whether the CMO's data-integrity posture is adequate; name any weakness

## Capacity and continuity
- Whether declared capacity and redundancy support the committed volume

## Quality-agreement coverage
- Whether an executed quality agreement defines the responsibilities and CAPA

## Findings and recommendations
- Specific findings (which observation, system, CAPA) and the qualification impact

## Claims
- Specific factual claims about the supplied evidence that ground the review
"""

_REVISION_PROMPT = """\
Revise the CMO / CDMO qualification review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact audit observation, data-integrity
weakness, or capacity gap from the supplied evidence; do not assert a fact the
evidence does not show.
"""


@dataclass
class CMOQualificationRequest:
    """Structured input for the CMO / CDMO qualification review workflow."""

    supplier_description: str
    """Generic CMO/CDMO category and scope of work."""

    audit_findings_summary: str
    """Last audit observations and their classification."""

    gmp_history: str
    """Regulatory inspection history (findings, warning letters)."""

    data_integrity_posture: str
    """The CMO's data-integrity controls and posture."""

    capacity_assessment: str
    """Declared vs required capacity and continuity."""

    quality_agreement_status: str
    """Status of the executed quality agreement."""

    capa_status: str
    """Open CAPAs from prior audits and their state."""

    technical_transfer_readiness: str
    """Readiness for the technical transfer / process validation."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Supplier description: {self.supplier_description[:cap]}",
            f"Audit findings summary: {self.audit_findings_summary[:cap]}",
            f"GMP history: {self.gmp_history[:cap]}",
            f"Data integrity posture: {self.data_integrity_posture[:cap]}",
            f"Capacity assessment: {self.capacity_assessment[:cap]}",
            f"Quality agreement status: {self.quality_agreement_status[:cap]}",
            f"CAPA status: {self.capa_status[:cap]}",
            f"Technical transfer readiness: {self.technical_transfer_readiness[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "GMP-GAP FLAGS:",
    "DATA-INTEGRITY FLAGS:",
    "CAPACITY FLAGS:",
)


class CMOQualificationWorkflow(BaseWorkflow):
    """
    Adversarial CMO / CDMO qualification review: executor argues the supplier is
    qualified → reviewer challenges unremediated GMP gaps, data-integrity
    weaknesses, and inadequate capacity → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero GMP-GAP FLAGS
        AND zero DATA-INTEGRITY FLAGS
        AND zero CAPACITY FLAGS

    No reviewer veto — qualification findings drive CAPA, not an irreversible halt.
    """

    async def run(  # type: ignore[override]
        self,
        request: CMOQualificationRequest,
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
                criteria=_CMO_REVIEW_CRITERIA,
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

        cmo_checklist = self._build_cmo_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "supplier_description": sanitize_for_prompt(
                    request.supplier_description, max_chars=200
                ),
                "gmp_gap_flags": list(dict.fromkeys(accumulated["GMP-GAP FLAGS:"])),
                "data_integrity_flags": list(
                    dict.fromkeys(accumulated["DATA-INTEGRITY FLAGS:"])
                ),
                "capacity_flags": list(dict.fromkeys(accumulated["CAPACITY FLAGS:"])),
                "cmo_checklist": cmo_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "GMP-GAP FLAGS:": (
                "⚠️  GMP-GAP FLAGS (name the GMP deficiency and its remediation/CAPA "
                "state; do not assert closure the evidence does not show):"
            ),
            "DATA-INTEGRITY FLAGS:": (
                "⚠️  DATA-INTEGRITY FLAGS (name the data-integrity weakness at the "
                "CMO that remains unaddressed):"
            ),
            "CAPACITY FLAGS:": (
                "⚠️  CAPACITY FLAGS (name the capacity/continuity gap against the "
                "committed volume and timeline):"
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
    def _build_cmo_checklist(
        request: CMOQualificationRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Supplier Quality / External Manufacturing]")
        if accumulated["GMP-GAP FLAGS:"]:
            checklist.append(
                "[ ] Remediate or place under time-bound CAPA each flagged GMP "
                "deficiency before qualification"
            )
        if accumulated["DATA-INTEGRITY FLAGS:"]:
            checklist.append(
                "[ ] Close each flagged data-integrity weakness at the CMO before "
                "qualification"
            )
        if accumulated["CAPACITY FLAGS:"]:
            checklist.append(
                "[ ] Resolve each flagged capacity/continuity gap against the "
                "committed volume and timeline"
            )
        checklist.append(
            "[ ] Confirm every finding resolves against the controlled "
            "qualification system, not the caller summary"
        )
        checklist.append(
            "[ ] Confirm an executed quality agreement covers responsibilities "
            "and CAPA linkage"
        )
        checklist.append(
            "[ ] Obtain Supplier Quality sign-off before the CMO is approved for "
            "the intended scope"
        )
        return checklist
