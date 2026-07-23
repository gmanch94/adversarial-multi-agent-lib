"""
Workflow — Computer System Validation (CSV) Review (Lifesciences · Cross-segment)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for risk-based computer system
validation under GAMP 5 / 21 CFR Part 11 / EU Annex 11. Executor reviews whether
the validation effort matches the system's GxP intended use and category, with
full requirement-to-test traceability; reviewer (recommended: different model
family) challenges intended-use/scope mismatches, orphan requirements, and
missing test evidence.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Validation-lifecycle tool — requirements, risk assessments, and test
       evidence should be pulled live from the controlled validation-lifecycle
       management system, not caller-pasted text.
    2. Requirements/traceability tool — the trace matrix should resolve against
       the controlled requirements repository, not a manual summary.
    3. Test-management system — IQ/OQ/PQ execution evidence should resolve to
       controlled, approved test records with signatures.
    4. GAMP 5 risk framework — categorization and validation rigor should be
       set by the controlled risk framework, not caller free text.
    5. Qualified approver gate — every AI-suggested finding must be reviewed
       and confirmed by a qualified CSV / Quality IT approver; output is never
       a validation certificate of record.
    6. Dedicated third-model validation auditor — production should use a
       separately configured auditor model for traceability bias detection.
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

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated computer system validation review is "
    "decision-support, not a validation deliverable and not a regulatory "
    "record. A qualified CSV / Quality IT approver must independently verify "
    "every requirement-to-test link and evidence citation against the "
    "controlled validation system before release. Not legal or medical advice."
)

_CSV_REVIEW_CRITERIA = """\
Evaluate this computer system validation review on five dimensions. Score each 0–10.

1. INTENDED-USE & RISK FIT (30%) — CRITICAL
   Is the validation scope matched to the stated GxP intended use and GAMP 5
   category (effort proportionate to risk and configuration/customization)?
   Penalise scope that under- or over-shoots the intended use. Flag mismatches
   under INTENDED-USE FLAGS:.

2. REQUIREMENT-TEST TRACEABILITY (25%) — CRITICAL
   Does every requirement (URS/FS) trace to at least one executed test, and
   every test back to a requirement? Penalise orphan requirements and orphan
   tests. Flag each broken link under TRACE-GAP FLAGS:.

3. TEST EVIDENCE (20%) — CRITICAL
   Does every requirement asserted verified have cited IQ/OQ/PQ execution
   evidence? Penalise requirements marked verified without cited, approved
   evidence. Flag gaps under TEST-EVIDENCE FLAGS:.

4. RISK-BASED VALIDATION RIGOR (15%)
   Is the depth of testing proportionate to the GAMP 5 category and patient/
   product risk (Category 3 vs 4 vs 5 effort)? Penalise a rigor level that does
   not follow from the risk assessment.

5. ACTIONABILITY (10%)
   Is each finding specific enough for the CSV team to close (which requirement,
   which test, what evidence is missing)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero INTENDED-USE FLAGS AND zero TRACE-GAP FLAGS AND zero
TEST-EVIDENCE FLAGS: ready for CSV / Quality IT sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  INTENDED-USE FLAGS: [bullet list, or "None detected"]
  TRACE-GAP FLAGS: [bullet list, or "None detected"]
  TEST-EVIDENCE FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are reviewing computer system validation for a CSV / Quality IT approver to
review. You have no stake in the outcome. Review whether the validation effort
matches the system's stated GxP intended use and GAMP 5 category, with full
requirement-to-test traceability — grounded only in the supplied evidence.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert a requirement, test, or
evidence link that is not present in the material below.

VALIDATION PACKAGE EXCERPT (caller-supplied — verify against the controlled
validation system before acting):
{request_text}

{wiki_context}

Produce a review with:

## Intended-use and risk fit
- Whether the validation scope matches the stated intended use and GAMP category

## Requirement-to-test traceability
- Requirement-to-test and test-to-requirement link status; name every orphan

## Test-evidence coverage
- Each verified requirement and its cited IQ/OQ/PQ evidence (or the gap)

## Risk-based rigor
- Whether test depth is proportionate to the GAMP category and risk

## Findings and recommendations
- Specific, closeable findings (which requirement, which test, what evidence)

## Claims
- Specific factual claims about the supplied evidence that ground the review
"""

_REVISION_PROMPT = """\
Revise the computer system validation review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact requirement, test, or evidence gap from
the supplied validation package; do not assert a link the evidence does not show.
"""


@dataclass
class ComputerSystemValidationRequest:
    """Structured input for the computer system validation review workflow."""

    system_description: str
    """Generic system category and its GxP use."""

    intended_use_statement: str
    """The stated GxP intended use of the system."""

    gamp_category: str
    """Caller's GAMP 5 category claim (e.g. Category 3 / 4 / 5)."""

    requirements_summary: str
    """User/functional requirements (URS/FS) in scope."""

    risk_assessment_summary: str
    """The risk assessment driving validation rigor."""

    test_evidence_summary: str
    """IQ/OQ/PQ execution evidence available."""

    trace_matrix_summary: str
    """Caller's summary of requirement-to-test links."""

    change_control_summary: str
    """Change-control status for the validated state."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"System description: {self.system_description[:cap]}",
            f"Intended use statement: {self.intended_use_statement[:cap]}",
            f"GAMP category: {self.gamp_category[:cap]}",
            f"Requirements summary: {self.requirements_summary[:cap]}",
            f"Risk assessment summary: {self.risk_assessment_summary[:cap]}",
            f"Test evidence summary: {self.test_evidence_summary[:cap]}",
            f"Trace matrix summary: {self.trace_matrix_summary[:cap]}",
            f"Change control summary: {self.change_control_summary[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "INTENDED-USE FLAGS:",
    "TRACE-GAP FLAGS:",
    "TEST-EVIDENCE FLAGS:",
)


class ComputerSystemValidationWorkflow(BaseWorkflow):
    """
    Adversarial computer system validation review: executor reviews scope +
    traceability + evidence → reviewer challenges intended-use/scope mismatches,
    orphan requirements, and missing test evidence → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero INTENDED-USE FLAGS
        AND zero TRACE-GAP FLAGS
        AND zero TEST-EVIDENCE FLAGS

    No reviewer veto — validation findings drive rework, not an irreversible halt.
    """

    async def run(  # type: ignore[override]
        self,
        request: ComputerSystemValidationRequest,
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
                criteria=_CSV_REVIEW_CRITERIA,
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

        csv_checklist = self._build_csv_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "system_description": sanitize_for_prompt(
                    request.system_description, max_chars=200
                ),
                "intended_use_flags": list(
                    dict.fromkeys(accumulated["INTENDED-USE FLAGS:"])
                ),
                "trace_gap_flags": list(dict.fromkeys(accumulated["TRACE-GAP FLAGS:"])),
                "test_evidence_flags": list(
                    dict.fromkeys(accumulated["TEST-EVIDENCE FLAGS:"])
                ),
                "csv_checklist": csv_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "INTENDED-USE FLAGS:": (
                "⚠️  INTENDED-USE FLAGS (name the scope/intended-use or GAMP-category "
                "mismatch; do not assert a use the evidence does not state):"
            ),
            "TRACE-GAP FLAGS:": (
                "⚠️  TRACE-GAP FLAGS (name the orphan requirement or orphan test; do "
                "not assert a link absent from the supplied trace matrix):"
            ),
            "TEST-EVIDENCE FLAGS:": (
                "⚠️  TEST-EVIDENCE FLAGS (cite the missing IQ/OQ/PQ evidence for the "
                "named requirement):"
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
    def _build_csv_checklist(
        request: ComputerSystemValidationRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Computer System Validation / Quality IT]")
        if accumulated["INTENDED-USE FLAGS:"]:
            checklist.append(
                "[ ] Reconcile validation scope with the stated intended use and "
                "GAMP category for each flagged mismatch"
            )
        if accumulated["TRACE-GAP FLAGS:"]:
            checklist.append(
                "[ ] Resolve every flagged orphan requirement/test in the "
                "controlled trace matrix before release"
            )
        if accumulated["TEST-EVIDENCE FLAGS:"]:
            checklist.append(
                "[ ] Attach the missing IQ/OQ/PQ evidence for each flagged "
                "requirement; confirm it is approved and controlled"
            )
        checklist.append(
            "[ ] Confirm requirement-to-test traceability resolves against the "
            "controlled validation system, not the caller summary"
        )
        checklist.append(
            "[ ] Confirm test depth is proportionate to the GAMP category and risk"
        )
        checklist.append(
            "[ ] Confirm change control holds the validated state before release"
        )
        checklist.append(
            "[ ] Obtain CSV / Quality IT sign-off before the system is released "
            "for GxP use"
        )
        return checklist
