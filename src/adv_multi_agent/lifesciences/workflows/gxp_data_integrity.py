"""
Workflow — GxP Data Integrity Assessment (Lifesciences · Cross-segment)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for GxP data-integrity review
against ALCOA+ principles. Executor assesses whether GxP records are
attributable, legible, contemporaneous, original, accurate (and complete,
consistent, enduring, available); reviewer (recommended: different model family)
challenges unmet ALCOA+ attributes, audit-trail gaps, and attribution failures.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Source-system integration — GxP records should be read live from the
       controlled source systems (LIMS / MES / historian / CDS), not
       caller-pasted text.
    2. Audit-trail review tooling — audit trails should resolve against the
       eQMS audit-trail review workflow with effective dates, not a summary.
    3. ALCOA+ assessment framework — the assessment should run against the
       controlled data-integrity framework, not caller free text.
    4. Data-governance council — every finding must be adjudicated by the
       data-governance council; output is never a data-integrity attestation
       of record.
    5. Qualified approver gate — every AI-suggested finding must be reviewed
       and confirmed by a qualified QA / Data Integrity lead before any CAPA
       or disposition.
    6. Dedicated third-model data-integrity auditor — production should use a
       separately configured auditor model for ALCOA+ bias detection. See
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

# L-PC-3: per-field cap — prevents a single oversized field crowding out
# later fields when the concatenated prompt is trimmed by sanitize_for_prompt.
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated GxP data-integrity assessment is "
    "decision-support, not a data-integrity attestation and not a regulatory "
    "record. A qualified QA / Data Integrity lead must independently verify "
    "every ALCOA+ finding against the controlled source systems before any "
    "CAPA or disposition. Not legal or medical advice."
)

_GXP_REVIEW_CRITERIA = """\
Evaluate this GxP data-integrity assessment on five dimensions. Score each 0–10.

1. ALCOA+ COMPLIANCE (30%) — CRITICAL
   Is every ALCOA+ attribute (attributable, legible, contemporaneous, original,
   accurate — plus complete, consistent, enduring, available) demonstrably met
   for the records described? Penalise any attribute asserted met without
   evidence. Flag each unmet attribute under ALCOA FLAGS:.

2. AUDIT-TRAIL ADEQUACY (25%) — CRITICAL
   Is the audit trail enabled, tamper-evident, and actually reviewed (not merely
   available)? Penalise audit trails that are disabled, editable, or never
   reviewed. Flag gaps under AUDIT-TRAIL FLAGS:.

3. ATTRIBUTION & ACCESS CONTROL (20%) — CRITICAL
   Is every action uniquely attributable to a person and a time, with adequate
   segregation of duties and no shared logins or back-dating? Penalise
   attribution failures. Flag gaps under ATTRIBUTION FLAGS:.

4. DATA-LIFECYCLE COVERAGE (15%)
   Does the assessment cover the full data lifecycle (create → process → review
   → report → retain → retrieve → archive)? Penalise a lifecycle stage left
   unassessed.

5. ACTIONABILITY (10%)
   Is each finding specific enough for QA to remediate (which record, which
   attribute, what evidence is missing)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero ALCOA FLAGS AND zero AUDIT-TRAIL FLAGS AND zero
ATTRIBUTION FLAGS: ready for QA / Data Integrity sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  ALCOA FLAGS: [bullet list, or "None detected"]
  AUDIT-TRAIL FLAGS: [bullet list, or "None detected"]
  ATTRIBUTION FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are assessing GxP data integrity for a QA / Data Integrity lead to review.
You have no stake in the outcome. Assess the records against ALCOA+ principles
using the supplied evidence — not against general industry norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert an ALCOA+ attribute is
met or unmet beyond what the records, audit-trail summary, access-control
summary, and lifecycle evidence below support.

GxP DATA-INTEGRITY EVIDENCE (caller-supplied — verify against the controlled
source systems before acting):
{request_text}

{wiki_context}

Produce an assessment with:

## ALCOA+ attribute assessment
- Each ALCOA+ attribute and whether it is met, with the supporting evidence

## Audit-trail review
- Audit-trail configuration, tamper-evidence, and review evidence (or the gap)

## Attribution and access control
- Unique attribution, segregation of duties, shared-login / back-dating risks

## Data-lifecycle coverage
- Each lifecycle stage and its integrity controls (or the gap)

## Findings and remediation
- Specific, remediable findings (which record, which attribute, what evidence)

## Claims
- Specific factual claims about the supplied evidence that ground the assessment
"""

_REVISION_PROMPT = """\
Revise the GxP data-integrity assessment based on reviewer critique.

ORIGINAL ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact record and the ALCOA+ attribute,
audit-trail gap, or attribution failure from the supplied evidence; do not
assert an attribute state the evidence does not support.
"""


@dataclass
class GxPDataIntegrityRequest:
    """Structured input for the GxP data-integrity assessment workflow."""

    system_description: str
    """Generic GxP system / record category and its role."""

    record_type: str
    """Electronic / paper / hybrid, and which GxP records are in scope."""

    audit_trail_summary: str
    """Audit-trail configuration and the evidence it is reviewed."""

    access_control_summary: str
    """User roles, segregation of duties, and login controls."""

    data_lifecycle_summary: str
    """How the records are handled from creation through archive."""

    alcoa_assessment: str
    """Caller's ALCOA+ self-assessment for the records."""

    deviations_investigations: str
    """Known data-integrity deviations and their CAPA status."""

    review_by_exception_summary: str
    """Basis for any review-by-exception approach."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"System description: {self.system_description[:cap]}",
            f"Record type: {self.record_type[:cap]}",
            f"Audit trail summary: {self.audit_trail_summary[:cap]}",
            f"Access control summary: {self.access_control_summary[:cap]}",
            f"Data lifecycle summary: {self.data_lifecycle_summary[:cap]}",
            f"ALCOA assessment: {self.alcoa_assessment[:cap]}",
            f"Deviations and investigations: {self.deviations_investigations[:cap]}",
            f"Review by exception summary: {self.review_by_exception_summary[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "ALCOA FLAGS:",
    "AUDIT-TRAIL FLAGS:",
    "ATTRIBUTION FLAGS:",
)


class GxPDataIntegrityWorkflow(BaseWorkflow):
    """
    Adversarial GxP data-integrity assessment: executor assesses records against
    ALCOA+ → reviewer challenges unmet attributes, audit-trail gaps, and
    attribution failures → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero ALCOA FLAGS
        AND zero AUDIT-TRAIL FLAGS
        AND zero ATTRIBUTION FLAGS

    No reviewer veto — data-integrity findings drive CAPA, not an irreversible halt.
    """

    async def run(  # type: ignore[override]
        self,
        request: GxPDataIntegrityRequest,
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
                criteria=_GXP_REVIEW_CRITERIA,
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

        gxp_checklist = self._build_gxp_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "system_description": sanitize_for_prompt(
                    request.system_description, max_chars=200
                ),
                "alcoa_flags": list(dict.fromkeys(accumulated["ALCOA FLAGS:"])),
                "audit_trail_flags": list(
                    dict.fromkeys(accumulated["AUDIT-TRAIL FLAGS:"])
                ),
                "attribution_flags": list(
                    dict.fromkeys(accumulated["ATTRIBUTION FLAGS:"])
                ),
                "gxp_checklist": gxp_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "ALCOA FLAGS:": (
                "⚠️  ALCOA FLAGS (name the record and the unmet ALCOA+ attribute; "
                "do not assert an attribute state the supplied evidence lacks):"
            ),
            "AUDIT-TRAIL FLAGS:": (
                "⚠️  AUDIT-TRAIL FLAGS (cite the specific audit-trail gap — disabled, "
                "editable, or not reviewed — for the named record):"
            ),
            "ATTRIBUTION FLAGS:": (
                "⚠️  ATTRIBUTION FLAGS (cite the specific attribution failure — shared "
                "login, missing timestamp, back-dating — for the named action):"
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
    def _build_gxp_checklist(
        request: GxPDataIntegrityRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Quality Assurance / Data Integrity Lead]")
        if accumulated["ALCOA FLAGS:"]:
            checklist.append(
                "[ ] Remediate each flagged ALCOA+ attribute against the "
                "controlled source system before disposition"
            )
        if accumulated["AUDIT-TRAIL FLAGS:"]:
            checklist.append(
                "[ ] Close each flagged audit-trail gap (enable, protect, or "
                "evidence the review) for the named record"
            )
        if accumulated["ATTRIBUTION FLAGS:"]:
            checklist.append(
                "[ ] Resolve each flagged attribution failure (retire shared "
                "logins, restore timestamps, investigate back-dating)"
            )
        checklist.append(
            "[ ] Confirm every finding resolves against the controlled source "
            "systems (LIMS / MES / historian / CDS), not the caller summary"
        )
        checklist.append(
            "[ ] Open or link a CAPA for each unresolved data-integrity finding"
        )
        checklist.append(
            "[ ] Escalate systemic findings to the data-governance council"
        )
        checklist.append(
            "[ ] Obtain QA / Data Integrity sign-off before any batch or record "
            "disposition"
        )
        return checklist
