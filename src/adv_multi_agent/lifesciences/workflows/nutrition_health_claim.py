"""
Workflow — Nutrition Health-Claim Review (Lifesciences · Nutrition)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for nutrition label-claim
review. Executor assesses structure-function / health claims, nutrient adequacy,
and allergen declarations; reviewer (recommended: different model family)
challenges unsubstantiated claims, inadequate nutrient profiles, and undeclared
allergens.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Substantiation-dossier repository — claim evidence should resolve to a
       controlled substantiation-dossier system, not caller-pasted summaries.
    2. Structure-function-claim notification log — every structure-function
       claim should reconcile against the controlled 30-day notification log.
    3. Nutrient database — the nutrient profile should resolve against the
       controlled composition database, not a caller-supplied summary.
    4. Allergen-control plan — allergen and cross-contact statements should be
       driven by the live allergen-control / HACCP plan, not free text.
    5. Qualified approver gate — every AI-suggested claim conclusion must be
       reviewed and confirmed by a qualified Nutrition Regulatory / Scientific
       Affairs reviewer before any label is released.
    6. Dedicated third-model claim auditor — production should use a separately
       configured auditor model for claim-substantiation bias detection.
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
    "ADVISORY ONLY — This AI-generated nutrition label-claim review is "
    "decision-support, not a regulatory filing or a substantiation decision. "
    "A qualified Nutrition Regulatory / Scientific Affairs reviewer must "
    "independently verify claim substantiation, nutrient adequacy, and allergen "
    "declarations before any label is released. Not legal or medical advice."
)

_NUTRITION_REVIEW_CRITERIA = """\
Evaluate this nutrition label-claim review on five dimensions. Score each 0–10.

1. CLAIM SUBSTANTIATION (30%) — CRITICAL
   Does every structure-function claim have competent-reliable scientific
   evidence in the substantiation dossier, and every disease (health) claim an
   authorization? Penalise a disease claim made as a structure-function claim
   without authorization. Flag gaps under CLAIM-SUBSTANTIATION FLAGS:.

2. NUTRIENT ADEQUACY (25%) — CRITICAL
   Is the nutrient profile adequate against the applicable requirement for the
   product category and target population (e.g. infant-formula nutrient
   minimums, 21 CFR 107)? Penalise a profile below a required minimum. Flag
   gaps under NUTRIENT-ADEQUACY FLAGS:.

3. ALLERGEN DECLARATION (20%) — CRITICAL
   Is every major allergen declared, and is a cross-contact statement present
   where the process warrants it? Penalise an undeclared major allergen. Flag
   gaps under ALLERGEN FLAGS:.

4. CLAIM-CATEGORY ROUTING (15%)
   Is each claim correctly categorised (structure-function vs nutrient-content
   vs health) and does the label meet that category's requirements? Penalise
   mis-categorised claims.

5. ACTIONABILITY (10%)
   Is each finding specific enough for a regulatory reviewer to resolve (which
   claim, which nutrient, which allergen)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero CLAIM-SUBSTANTIATION FLAGS AND zero NUTRIENT-ADEQUACY
FLAGS AND zero ALLERGEN FLAGS: ready for Nutrition Regulatory sign-off.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  CLAIM-SUBSTANTIATION FLAGS: [bullet list, or "None detected"]
  NUTRIENT-ADEQUACY FLAGS: [bullet list, or "None detected"]
  ALLERGEN FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are reviewing nutrition label claims for a Nutrition Regulatory reviewer to
sign off. You have no stake in the outcome. Assess each claim, the nutrient
profile, and the allergen declaration against the supplied substantiation
dossier summary — not against general nutrition norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert substantiation, nutrient
adequacy, or an allergen declaration that is not present in the dossier summary,
nutrient profile, or allergen declaration below.

LABEL-CLAIM PACKAGE (caller-supplied — verify against the controlled dossier,
nutrient database, and allergen-control plan before acting):
{request_text}

{wiki_context}

Produce a review with:

## Claim inventory and categorisation
- Each claim, its category (structure-function / nutrient-content / health)

## Substantiation assessment
- Each structure-function / health claim and its cited dossier evidence (or gap)

## Nutrient adequacy
- The nutrient profile against the applicable minimum for the population (or gap)

## Allergen declaration
- Each major allergen declared and the cross-contact statement (or gap)

## Findings and recommendations
- Specific, closeable findings (which claim, which nutrient, which allergen)

## Claims
- Specific factual claims about the dossier evidence that ground the review
"""

_REVISION_PROMPT = """\
Revise the nutrition label-claim review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the specific dossier evidence / nutrient
requirement / allergen source; do not assert substantiation absent from the
supplied dossier summary.
"""


@dataclass
class NutritionClaimRequest:
    """Structured input for the nutrition health-claim review workflow."""

    product_category: str
    """Generic product category and form (e.g. adult nutritional shake, RTD)."""

    claim_set: str
    """Claims on the label (IDs + text; structure-function / nutrient / health)."""

    substantiation_dossier_summary: str
    """Summary of the substantiation dossier evidence per claim."""

    target_population: str
    """Intended population (e.g. adults 19+, infants, pediatric)."""

    nutrient_profile: str
    """Nutrient profile per serving (energy, macros, vitamins/minerals + DV)."""

    allergen_declaration: str
    """Declared allergens and any cross-contact statement."""

    infant_formula_flag: str
    """Whether the product is an infant formula (drives 21 CFR 107 minimums)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product category: {self.product_category[:cap]}",
            f"Claim set: {self.claim_set[:cap]}",
            f"Substantiation dossier summary: {self.substantiation_dossier_summary[:cap]}",
            f"Target population: {self.target_population[:cap]}",
            f"Nutrient profile: {self.nutrient_profile[:cap]}",
            f"Allergen declaration: {self.allergen_declaration[:cap]}",
            f"Infant formula flag: {self.infant_formula_flag[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "CLAIM-SUBSTANTIATION FLAGS:",
    "NUTRIENT-ADEQUACY FLAGS:",
    "ALLERGEN FLAGS:",
)


class NutritionHealthClaimWorkflow(BaseWorkflow):
    """
    Adversarial nutrition health-claim review: executor assesses claim
    substantiation, nutrient adequacy, and allergen declarations → reviewer
    challenges unsubstantiated claims, inadequate profiles, and undeclared
    allergens → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero CLAIM-SUBSTANTIATION FLAGS
        AND zero NUTRIENT-ADEQUACY FLAGS
        AND zero ALLERGEN FLAGS

    No reviewer veto — label-claim corrections are reversible before release.
    """

    async def run(  # type: ignore[override]
        self,
        request: NutritionClaimRequest,
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
                criteria=_NUTRITION_REVIEW_CRITERIA,
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

        nutrition_checklist = self._build_nutrition_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "product_category": sanitize_for_prompt(
                    request.product_category, max_chars=200
                ),
                "claim_substantiation_flags": list(
                    dict.fromkeys(accumulated["CLAIM-SUBSTANTIATION FLAGS:"])
                ),
                "nutrient_adequacy_flags": list(
                    dict.fromkeys(accumulated["NUTRIENT-ADEQUACY FLAGS:"])
                ),
                "allergen_flags": list(dict.fromkeys(accumulated["ALLERGEN FLAGS:"])),
                "nutrition_checklist": nutrition_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "CLAIM-SUBSTANTIATION FLAGS:": (
                "⚠️  CLAIM-SUBSTANTIATION FLAGS (cite competent-reliable evidence or "
                "the required notification for the named claim; do not assert "
                "substantiation absent from the supplied dossier):"
            ),
            "NUTRIENT-ADEQUACY FLAGS:": (
                "⚠️  NUTRIENT-ADEQUACY FLAGS (cite the applicable minimum, e.g. 21 CFR "
                "107 for infant formula, for the named nutrient):"
            ),
            "ALLERGEN FLAGS:": (
                "⚠️  ALLERGEN FLAGS (name the undeclared major allergen or the missing "
                "cross-contact statement):"
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
    def _build_nutrition_checklist(
        request: NutritionClaimRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Nutrition Regulatory + Scientific Affairs]")
        if accumulated["CLAIM-SUBSTANTIATION FLAGS:"]:
            checklist.append(
                "[ ] Attach competent-reliable evidence for each flagged "
                "structure-function claim; confirm a disease/health claim has "
                "authorization before use"
            )
        if accumulated["NUTRIENT-ADEQUACY FLAGS:"]:
            checklist.append(
                "[ ] Reconcile each flagged nutrient against the applicable "
                "minimum for the target population before label release"
            )
        if accumulated["ALLERGEN FLAGS:"]:
            checklist.append(
                "[ ] Declare each flagged major allergen and add the required "
                "cross-contact statement before label release"
            )
        checklist.append(
            "[ ] Verify each structure-function claim against the substantiation "
            "dossier"
        )
        checklist.append(
            "[ ] Confirm a disease/health claim has authorization before use"
        )
        checklist.append(
            "[ ] Confirm nutrient profile meets the applicable minimum for the "
            "population"
        )
        checklist.append(
            "[ ] Confirm all major allergens are declared and cross-contact stated"
        )
        checklist.append(
            "[ ] Obtain Nutrition Regulatory sign-off before label release"
        )
        return checklist
