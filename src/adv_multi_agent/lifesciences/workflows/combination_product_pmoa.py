"""
Workflow — Combination-Product PMOA Routing (Lifesciences · Cross-segment)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for combination-product
jurisdictional routing under 21 CFR 3. Executor derives the primary mode of
action (PMOA), proposes a lead center (CDER / CBER / CDRH) and a submission
pathway; reviewer (recommended: different model family) challenges a PMOA that
does not follow from the mechanism, a lead center inconsistent with the PMOA,
and a pathway inconsistent with the center.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. 21 CFR 3 reference — the primary-mode-of-action determination should
       resolve against the controlled 21 CFR Part 3 rule text and current
       Office of Combination Products guidance, not caller-pasted summaries.
    2. RFD-precedent database — cited precedents should resolve against the
       controlled Request-for-Designation determination database, not
       caller-supplied text.
    3. Jurisdictional-determination archive — every routing conclusion should
       reconcile against the controlled jurisdictional-determination archive.
    4. Qualified strategist gate — every AI-suggested PMOA / center / pathway
       must be reviewed and confirmed by a qualified Regulatory Strategy lead
       before any submission or Request for Designation.
    5. Dedicated third-model routing auditor — production should use a
       separately configured auditor model for center-assignment bias
       detection. See ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated primary-mode-of-action analysis is "
    "decision-support, not a Request for Designation and not a jurisdictional "
    "determination. A qualified Regulatory Strategy lead must independently "
    "confirm the PMOA, lead center, and pathway under 21 CFR 3 before any "
    "submission. Not legal or medical advice."
)

_PMOA_REVIEW_CRITERIA = """\
Evaluate this combination-product PMOA analysis on five dimensions. Score each 0–10.

1. PMOA DETERMINATION (30%) — CRITICAL
   Is the primary mode of action consistent with the described therapeutic
   mechanism and each constituent's contribution? Penalise a PMOA that does not
   follow from the mechanism (e.g. a drug PMOA where the device provides the
   primary therapeutic effect). Flag under PMOA FLAGS:.

2. LEAD-CENTER ASSIGNMENT (25%) — CRITICAL
   Does the proposed lead center (CDER / CBER / CDRH) follow from the PMOA?
   Penalise a center assignment inconsistent with the determined PMOA. Flag
   under LEAD-CENTER FLAGS:.

3. PATHWAY CONSISTENCY (20%) — CRITICAL
   Is the proposed submission pathway (NDA / BLA / PMA / 510(k)) consistent with
   the center and PMOA? Penalise a pathway that does not match. Flag under
   PATHWAY FLAGS:.

4. PRECEDENT ALIGNMENT (15%)
   Do cited precedent products / RFD determinations actually support the
   proposed routing? Penalise precedents that are not analogous.

5. ACTIONABILITY (10%)
   Is the recommendation specific enough for a regulatory strategist to act on
   (which center, which pathway, which precedent)? Penalise vague routing.

Overall score = weighted average.
Score >= 7.5 AND zero PMOA FLAGS AND zero LEAD-CENTER FLAGS AND zero PATHWAY
FLAGS: ready for Regulatory Strategy sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PMOA FLAGS: [bullet list, or "None detected"]
  LEAD-CENTER FLAGS: [bullet list, or "None detected"]
  PATHWAY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are analysing a combination product's primary mode of action for a
Regulatory Strategy lead to sign off. You have no stake in the outcome. Derive
the PMOA, lead center, and pathway from the supplied mechanism and each
constituent's contribution — not from general routing norms.

BASE EVERY CONCLUSION ON THE INPUT. Do not assert a PMOA, center, or pathway
that does not follow from the therapeutic mechanism, the constituent parts, or
each constituent's contribution below.

COMBINATION-PRODUCT PACKAGE (caller-supplied — verify against 21 CFR 3, the
RFD-precedent database, and the jurisdictional-determination archive before
acting):
{request_text}

{wiki_context}

Produce an analysis with:

## Constituent-part analysis
- Each constituent (drug / biologic / device) and its regulatory identity

## Primary mode of action
- The single mode providing the most important therapeutic action, derived from
  the mechanism and each constituent's contribution

## Lead-center determination
- The lead center (CDER / CBER / CDRH) that follows from the PMOA

## Submission pathway
- The pathway (NDA / BLA / PMA / 510(k)) consistent with the center and PMOA

## Precedent support
- Cited precedent products / RFD determinations and their analogy to this product

## Claims
- Specific factual claims about the mechanism and constituents that ground the
  routing
"""

_REVISION_PROMPT = """\
Revise the combination-product PMOA analysis based on reviewer critique.

ORIGINAL ANALYSIS:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: re-derive the PMOA from the therapeutic mechanism and
each constituent's contribution; do not assert a center/pathway that does not
follow from the PMOA.
"""


@dataclass
class PMOARequest:
    """Structured input for the combination-product PMOA routing workflow."""

    product_description: str
    """Generic product category and configuration (no brand)."""

    constituent_parts: str
    """Each constituent and its type (drug / biologic / device)."""

    therapeutic_effect_mechanism: str
    """How the product achieves its intended therapeutic effect."""

    each_constituent_contribution: str
    """The therapeutic contribution of each constituent part."""

    proposed_pmoa: str
    """The caller-proposed primary mode of action."""

    proposed_lead_center: str
    """The caller-proposed lead center (CDER / CBER / CDRH)."""

    precedent_products: str
    """Cited precedent products / RFD determinations for the proposed routing."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Constituent parts: {self.constituent_parts[:cap]}",
            f"Therapeutic effect mechanism: {self.therapeutic_effect_mechanism[:cap]}",
            f"Each constituent contribution: {self.each_constituent_contribution[:cap]}",
            f"Proposed PMOA: {self.proposed_pmoa[:cap]}",
            f"Proposed lead center: {self.proposed_lead_center[:cap]}",
            f"Precedent products: {self.precedent_products[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "PMOA FLAGS:",
    "LEAD-CENTER FLAGS:",
    "PATHWAY FLAGS:",
)


class CombinationProductPMOAWorkflow(BaseWorkflow):
    """
    Adversarial combination-product PMOA routing: executor derives the PMOA,
    lead center, and pathway → reviewer challenges a PMOA inconsistent with the
    mechanism, a center inconsistent with the PMOA, and a pathway inconsistent
    with the center → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero PMOA FLAGS
        AND zero LEAD-CENTER FLAGS
        AND zero PATHWAY FLAGS

    No reviewer veto — routing conclusions are advisory and reversible before a
    Request for Designation is filed.
    """

    async def run(  # type: ignore[override]
        self,
        request: PMOARequest,
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
                criteria=_PMOA_REVIEW_CRITERIA,
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

        pmoa_checklist = self._build_pmoa_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "product_description": sanitize_for_prompt(
                    request.product_description, max_chars=200
                ),
                "pmoa_flags": list(dict.fromkeys(accumulated["PMOA FLAGS:"])),
                "lead_center_flags": list(
                    dict.fromkeys(accumulated["LEAD-CENTER FLAGS:"])
                ),
                "pathway_flags": list(dict.fromkeys(accumulated["PATHWAY FLAGS:"])),
                "pmoa_checklist": pmoa_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "PMOA FLAGS:": (
                "⚠️  PMOA FLAGS (re-derive the primary mode of action from the "
                "therapeutic mechanism and each constituent's contribution; do "
                "not assert a PMOA the mechanism does not support):"
            ),
            "LEAD-CENTER FLAGS:": (
                "⚠️  LEAD-CENTER FLAGS (assign the lead center that follows from "
                "the determined PMOA under 21 CFR 3; do not assert a center the "
                "PMOA does not support):"
            ),
            "PATHWAY FLAGS:": (
                "⚠️  PATHWAY FLAGS (align the submission pathway with the center "
                "and PMOA; do not assert a pathway inconsistent with the center):"
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
    def _build_pmoa_checklist(
        request: PMOARequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Regulatory Strategy Lead]")
        if accumulated["PMOA FLAGS:"]:
            checklist.append(
                "[ ] Re-derive the PMOA from the therapeutic mechanism and each "
                "constituent's contribution for every flagged item"
            )
        if accumulated["LEAD-CENTER FLAGS:"]:
            checklist.append(
                "[ ] Confirm the lead center follows from the determined PMOA "
                "under 21 CFR 3 for every flagged item"
            )
        if accumulated["PATHWAY FLAGS:"]:
            checklist.append(
                "[ ] Confirm the submission pathway matches the lead center for "
                "every flagged item"
            )
        checklist.append(
            "[ ] Confirm the PMOA follows from the therapeutic mechanism and "
            "each constituent's contribution"
        )
        checklist.append(
            "[ ] Confirm the lead center follows from the determined PMOA"
        )
        checklist.append(
            "[ ] Confirm the submission pathway matches the lead center"
        )
        checklist.append(
            "[ ] Verify each cited precedent / RFD determination is analogous "
            "to this product"
        )
        checklist.append(
            "[ ] Obtain Regulatory Strategy sign-off before any submission or "
            "Request for Designation"
        )
        return checklist
