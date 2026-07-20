"""
Workflow — REMS Design Review (Lifesciences · Pharma)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for a Risk Evaluation and
Mitigation Strategy (REMS). Executor drafts the risk-to-element mapping,
burden assessment, and assessment plan; reviewer (recommended: different model
family) challenges elements not matched to a serious risk, disproportionate
access burden, and an assessment plan that cannot show the REMS meets its goals.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. REMS document-management + FDA submission system — the REMS document and
       its elements should resolve against the controlled REMS repository and
       submission gateway, not caller-pasted text.
    2. ETASU implementation infrastructure — prescriber/pharmacy certification
       and patient-enrollment status should resolve against the controlled
       certification registry, not a manual summary.
    3. Patient-registry system — enrollment/monitoring data should come from the
       live registry, not a caller-supplied reference.
    4. REMS assessment analytics — the assessment metrics/timetable should be
       computed against the controlled analytics system.
    5. Qualified approver gate — every AI-suggested REMS conclusion must be
       reviewed by a qualified REMS / Risk Management lead and Regulatory
       Affairs. Output is never an auto-submitted REMS.
    6. Dedicated third-model REMS auditor — production should use a separately
       configured auditor model for risk-to-element bias detection. See ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated REMS design review is decision-support, "
    "not a Risk Evaluation and Mitigation Strategy of record and not a regulatory "
    "submission. A qualified REMS / Risk Management lead and Regulatory Affairs "
    "must independently confirm every risk-to-element mapping, burden judgment, "
    "and assessment metric before any REMS is submitted. Not legal or medical advice."
)

_REMS_REVIEW_CRITERIA = """\
Evaluate this REMS design on five dimensions. Score each 0–10.

1. RISK-TO-ELEMENT FIT (30%) — CRITICAL
   Does every REMS element (Medication Guide, communication plan, ETASU) map to
   a serious risk it must mitigate, and does every serious risk have a mitigating
   element? Penalise an element with no matching risk, or a risk with no element.
   Flag each mismatch under RISK-MITIGATION FLAGS:.

2. ACCESS-BURDEN PROPORTIONALITY (25%) — CRITICAL
   Is each element's burden on patient access, providers, and the supply chain
   proportionate to the risk it mitigates? Penalise an element imposing
   disproportionate burden relative to the risk. Flag under BURDEN FLAGS:.

3. ASSESSMENT ADEQUACY (20%) — CRITICAL
   Do the assessment metrics and timetable actually measure whether the REMS
   meets its goals (risk reduction)? Penalise metrics/timetable that cannot show
   goal attainment. Flag gaps under ASSESSMENT-PLAN FLAGS:.

4. IMPLEMENTATION FEASIBILITY (15%)
   Are the elements operable in the real prescribing/dispensing supply chain?
   Penalise elements that cannot be implemented as described.

5. ACTIONABILITY (10%)
   Is each finding specific enough for the REMS lead to act on (which element,
   which risk, which metric)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero RISK-MITIGATION FLAGS AND zero BURDEN FLAGS AND zero
ASSESSMENT-PLAN FLAGS: ready for REMS lead sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  RISK-MITIGATION FLAGS: [bullet list, or "None detected"]
  BURDEN FLAGS: [bullet list, or "None detected"]
  ASSESSMENT-PLAN FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are reviewing a REMS design for a REMS / Risk Management lead to approve. You
have no stake in the outcome. Map each REMS element to the serious risk it
mitigates, weigh the access burden, and judge the assessment plan — grounded
only in the data supplied, not general REMS norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert a risk, element, or
metric that is not present below.

REMS DESIGN (caller-supplied — verify against the controlled REMS system before
acting):
{request_text}

{wiki_context}

Produce a review with:

## Risk-to-element mapping
- Each serious risk and the REMS element(s) that mitigate it; name every mismatch

## Access-burden assessment
- Each element and its burden on patients/providers/supply chain vs the risk

## Assessment-plan adequacy
- Whether the metrics and timetable can show the REMS meets its goals

## Implementation feasibility
- Whether each element is operable in the real supply chain

## Gaps and recommendations
- Specific, closeable gaps (which element, which risk, which metric)

## Claims
- Specific factual claims about the REMS design that ground the review
"""

_REVISION_PROMPT = """\
Revise the REMS design review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact risk↔element↔metric mismatch from the
supplied design; do not assert a risk or element that is not in the input.
"""


@dataclass
class REMSDesignRequest:
    """Structured input for the REMS design review workflow."""

    product_description: str
    """Generic product category and the serious risk the REMS addresses."""

    serious_risks: str
    """The specific serious risks the REMS must mitigate."""

    rems_goals: str
    """The risk-mitigation goals of the REMS."""

    rems_elements: str
    """REMS elements: Medication Guide, communication plan, ETASU."""

    etasu_summary: str
    """If ETASU: prescriber / pharmacy / patient requirements."""

    implementation_system: str
    """How the elements are operationalized across the supply chain."""

    assessment_plan: str
    """Timetable and metrics to assess REMS effectiveness."""

    burden_assessment: str
    """Caller's assessment of burden on patients / providers / supply chain."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Serious risks: {self.serious_risks[:cap]}",
            f"REMS goals: {self.rems_goals[:cap]}",
            f"REMS elements: {self.rems_elements[:cap]}",
            f"ETASU summary: {self.etasu_summary[:cap]}",
            f"Implementation system: {self.implementation_system[:cap]}",
            f"Assessment plan: {self.assessment_plan[:cap]}",
            f"Burden assessment: {self.burden_assessment[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "RISK-MITIGATION FLAGS:",
    "BURDEN FLAGS:",
    "ASSESSMENT-PLAN FLAGS:",
)


class REMSDesignWorkflow(BaseWorkflow):
    """
    Adversarial REMS design review: executor maps risks to elements, weighs
    burden, and judges the assessment plan → reviewer challenges element-to-risk
    mismatch, disproportionate burden, and inadequate assessment metrics → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero RISK-MITIGATION FLAGS
        AND zero BURDEN FLAGS
        AND zero ASSESSMENT-PLAN FLAGS

    No reviewer veto — REMS design corrections are reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: REMSDesignRequest,
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
                criteria=_REMS_REVIEW_CRITERIA,
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

        rems_checklist = self._build_rems_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "product_description": sanitize_for_prompt(
                    request.product_description, max_chars=200
                ),
                "risk_mitigation_flags": list(
                    dict.fromkeys(accumulated["RISK-MITIGATION FLAGS:"])
                ),
                "burden_flags": list(dict.fromkeys(accumulated["BURDEN FLAGS:"])),
                "assessment_plan_flags": list(
                    dict.fromkeys(accumulated["ASSESSMENT-PLAN FLAGS:"])
                ),
                "rems_checklist": rems_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "RISK-MITIGATION FLAGS:": (
                "⚠️  RISK-MITIGATION FLAGS (name the element with no matching serious "
                "risk, or the risk with no mitigating element):"
            ),
            "BURDEN FLAGS:": (
                "⚠️  BURDEN FLAGS (name the element whose access/provider burden is "
                "disproportionate to the risk it mitigates):"
            ),
            "ASSESSMENT-PLAN FLAGS:": (
                "⚠️  ASSESSMENT-PLAN FLAGS (name the metric or timetable gap that "
                "prevents showing the REMS meets its goals):"
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
    def _build_rems_checklist(
        request: REMSDesignRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: REMS / Risk Management Lead]"]
        if accumulated["RISK-MITIGATION FLAGS:"]:
            checklist.append(
                "[ ] Match every flagged REMS element to the serious risk it "
                "mitigates; cover every risk with an element"
            )
        if accumulated["BURDEN FLAGS:"]:
            checklist.append(
                "[ ] Right-size each flagged element so its access/provider burden "
                "is proportionate to the risk"
            )
        if accumulated["ASSESSMENT-PLAN FLAGS:"]:
            checklist.append(
                "[ ] Add assessment metrics that measure the REMS against its "
                "risk-reduction goals for each flag"
            )
        checklist.extend([
            "[ ] Confirm every serious risk maps to a REMS element and vice versa",
            "[ ] Confirm each ETASU element is operable in the real supply chain",
            "[ ] Confirm the assessment timetable can demonstrate goal attainment",
            "[ ] Obtain REMS lead and Regulatory Affairs sign-off before submission",
        ])
        return checklist
