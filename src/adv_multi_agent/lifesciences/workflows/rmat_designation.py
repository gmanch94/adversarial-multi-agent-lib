"""
Workflow — RMAT Designation Eligibility Assessment (Lifesciences · Advanced
Therapies / CGT)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to Regenerative
Medicine Advanced Therapy (RMAT) designation eligibility: executor argues the
product meets the three statutory prongs (regenerative-medicine therapy · serious
or life-threatening condition · preliminary clinical evidence indicating potential
to address an unmet need); reviewer (cross-model per ARIS §2.1) challenges
preliminary-clinical-evidence stretch, an overstated condition seriousness, and an
overstated unmet-need / available-therapy analysis.

No reviewer veto (D-LIFESCI-8): this is an advisory eligibility analysis.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Clinical-evidence database — the preliminary clinical evidence should
       resolve against the controlled clinical-study database, not a narrative.
    2. Expedited-program precedent archive — prior RMAT / breakthrough grants
       should reconcile against the controlled precedent archive.
    3. Unmet-need / therapy-landscape database — the available-therapy analysis
       should read the controlled landscape database, not caller-supplied text.
    4. FDA-interaction archive — prior meeting minutes / advice should resolve to
       the controlled interaction archive.
    5. Qualified RA approver gate — every AI-suggested eligibility conclusion must
       be confirmed by a qualified Regulatory Strategy lead. Output is never a
       filed designation request.
    6. Dedicated third-model eligibility auditor — production should use a
       separately configured auditor model for eligibility-inflation bias
       detection. See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import (
    extract_flags,
    sanitize_for_prompt,
    sanitize_request_text,
    truncate_flag_display,
)
from ...core.workflow import BaseWorkflow, WorkflowResult

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated RMAT designation eligibility assessment is "
    "decision-support, not a designation request and not an FDA determination. A "
    "qualified Regulatory Strategy lead must independently confirm the "
    "regenerative-medicine-therapy, serious-condition, and preliminary-evidence "
    "prongs before any designation request. Not legal or medical advice."
)

_RMAT_REVIEW_CRITERIA = """\
Evaluate this RMAT designation eligibility assessment on five dimensions. Score each 0–10.

1. PRELIMINARY CLINICAL EVIDENCE (30%) — CRITICAL
   Does the preliminary clinical evidence (n, design, endpoint, effect size)
   credibly indicate the therapy has the potential to address the condition?
   Penalise evidence that is underpowered, uncontrolled, or wrong-endpoint yet
   argued as sufficient. Flag under EVIDENCE-STRETCH FLAGS:.

2. SERIOUS OR LIFE-THREATENING CONDITION (25%) — CRITICAL
   Does the condition meet the serious-or-life-threatening bar as characterised?
   Penalise an overstated seriousness. Flag under SERIOUS-CONDITION FLAGS:.

3. UNMET MEDICAL NEED (20%) — CRITICAL
   Is the unmet-need claim supported against the available-therapy landscape?
   Penalise an overstated unmet need where adequate therapy exists. Flag under
   UNMET-NEED FLAGS:.

4. REGENERATIVE-MEDICINE-THERAPY QUALIFICATION (15%)
   Does the product qualify as a regenerative-medicine therapy (cell therapy,
   therapeutic tissue-engineering, human cell/tissue product, or combination)?
   Penalise a product that does not qualify.

5. ACTIONABILITY (10%)
   Is each finding specific enough for Regulatory Strategy to resolve (which
   study, which endpoint, which comparator)? Penalise vague findings.

Overall score = weighted average.
Score >= 7.5 AND zero EVIDENCE-STRETCH FLAGS AND zero SERIOUS-CONDITION FLAGS AND
zero UNMET-NEED FLAGS: ready for Regulatory Strategy sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  EVIDENCE-STRETCH FLAGS: [bullet list, or "None detected"]
  SERIOUS-CONDITION FLAGS: [bullet list, or "None detected"]
  UNMET-NEED FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are assessing eligibility for Regenerative Medicine Advanced Therapy (RMAT)
designation for a Regulatory Strategy lead to review. You have no stake in the
outcome. Assess the three statutory prongs — regenerative-medicine therapy,
serious or life-threatening condition, and preliminary clinical evidence
indicating potential to address an unmet need — against the supplied data only.

BASE EVERY FINDING ON THE INPUT DATA ONLY. Do not assert an eligibility
conclusion not grounded in the evidence below.

RMAT ELIGIBILITY DATA:
{request_text}

{wiki_context}

Produce an assessment with:

## Regenerative-medicine-therapy qualification
State whether the product qualifies as a regenerative-medicine therapy.

## Serious or life-threatening condition
State whether the condition meets the serious-or-life-threatening bar.

## Preliminary clinical evidence
Assess whether the preliminary clinical evidence credibly indicates potential to
address the condition; name any evidence gap.

## Unmet medical need
Assess the unmet-need claim against the available-therapy landscape.

## Eligibility conclusion
State whether the product appears eligible for RMAT designation, or the gaps that
prevent it.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this RMAT designation eligibility assessment based on reviewer critique.
Address EVERY issue, especially any EVIDENCE-STRETCH FLAGS, SERIOUS-CONDITION
FLAGS, or UNMET-NEED FLAGS.

ORIGINAL ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact study, endpoint, or comparator from the
input; do not assert eligibility the supplied evidence does not support.
"""


@dataclass
class RMATRequest:
    """Structured input for the RMAT designation eligibility assessment workflow."""

    product_description: str
    """Generic product category and regenerative-medicine therapy type."""

    serious_condition_rationale: str
    """Why the target condition is serious or life-threatening."""

    preliminary_clinical_evidence: str
    """Preliminary clinical evidence: n, design, endpoint, effect."""

    unmet_medical_need: str
    """The unmet medical need the therapy intends to address."""

    intent_to_address_unmet_need: str
    """How the therapy is intended to address the unmet need."""

    available_therapy_landscape: str
    """Currently available therapies for the condition."""

    prior_fda_interactions: str
    """Prior FDA interactions, meetings, or advice relevant to designation."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Serious-condition rationale: {self.serious_condition_rationale[:cap]}",
            f"Preliminary clinical evidence: {self.preliminary_clinical_evidence[:cap]}",
            f"Unmet medical need: {self.unmet_medical_need[:cap]}",
            f"Intent to address unmet need: {self.intent_to_address_unmet_need[:cap]}",
            f"Available therapy landscape: {self.available_therapy_landscape[:cap]}",
            f"Prior FDA interactions: {self.prior_fda_interactions[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "EVIDENCE-STRETCH FLAGS:",
    "SERIOUS-CONDITION FLAGS:",
    "UNMET-NEED FLAGS:",
)


class RMATDesignationWorkflow(BaseWorkflow):
    """
    Adversarial RMAT designation eligibility assessment: executor argues the three
    statutory prongs → reviewer challenges preliminary-clinical-evidence stretch,
    overstated condition seriousness, and an overstated unmet-need analysis →
    iterate.

    Convergence gate:
        score ≥ threshold
        AND zero EVIDENCE-STRETCH FLAGS
        AND zero SERIOUS-CONDITION FLAGS
        AND zero UNMET-NEED FLAGS

    No reviewer veto — an eligibility assessment is advisory; the designation
    decision rests with FDA.
    """

    async def run(  # type: ignore[override]
        self,
        request: RMATRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_request_text(request)
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
                criteria=_RMAT_REVIEW_CRITERIA,
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

        rmat_checklist = self._build_rmat_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "product_description": sanitize_for_prompt(
                    request.product_description, max_chars=200
                ),
                "evidence_stretch_flags": list(dict.fromkeys(accumulated["EVIDENCE-STRETCH FLAGS:"])),
                "serious_condition_flags": list(dict.fromkeys(accumulated["SERIOUS-CONDITION FLAGS:"])),
                "unmet_need_flags": list(dict.fromkeys(accumulated["UNMET-NEED FLAGS:"])),
                "rmat_checklist": rmat_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "EVIDENCE-STRETCH FLAGS:": (
                "⚠️  EVIDENCE-STRETCH FLAGS (cite the underpowered / uncontrolled / "
                "wrong-endpoint study argued as sufficient):"
            ),
            "SERIOUS-CONDITION FLAGS:": (
                "⚠️  SERIOUS-CONDITION FLAGS (cite the overstated seriousness vs the "
                "characterised condition):"
            ),
            "UNMET-NEED FLAGS:": (
                "⚠️  UNMET-NEED FLAGS (cite the available therapy that undercuts the "
                "unmet-need claim):"
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
    def _build_rmat_checklist(
        request: RMATRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Regulatory Strategy]"]
        if accumulated["EVIDENCE-STRETCH FLAGS:"]:
            checklist.append(
                "[ ] Strengthen or re-characterise the preliminary clinical evidence "
                "for each flagged stretch before requesting designation"
            )
        if accumulated["SERIOUS-CONDITION FLAGS:"]:
            checklist.append(
                "[ ] Re-characterise the condition seriousness for each flagged "
                "overstatement"
            )
        if accumulated["UNMET-NEED FLAGS:"]:
            checklist.append(
                "[ ] Reconcile the unmet-need claim against the available-therapy "
                "landscape for each flag"
            )
        checklist.extend([
            "[ ] Confirm the product qualifies as a regenerative-medicine therapy",
            "[ ] Confirm the preliminary clinical evidence credibly indicates potential",
            "[ ] Confirm the unmet-need claim holds against available therapy",
            "[ ] Obtain Regulatory Strategy sign-off before any designation request",
        ])
        return checklist
