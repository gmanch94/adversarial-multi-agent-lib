"""
Workflow — Private Label Product Decisions (Retail Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for private-label SKU
launch decisions. Executor drafts a launch recommendation; reviewer
(recommended: different model family per ARIS §2.1 principle 1)
challenges the cannibalization math, brand fit, and supply readiness.

Triple flag gate: CANNIBALIZATION FLAGS (total category margin drops
despite higher per-unit private-label margin) + BRAND FLAGS (positioning
conflicts with house-brand identity, or quality-assurance gap) + SUPPLY
FLAGS (co-manufacturer audit stale or capacity unproven).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Live cannibalization model — cannibalization_estimate is free-
       text; production requires a household-basket co-occurrence model
       that produces a per-SKU substitution matrix, not a narrated
       percentage.
    2. Brand-equity measurement — brand_positioning is caller-supplied;
       production requires a brand-tracking instrument (consumer panel
       or syndicated brand-equity feed) to test whether the proposed
       SKU positioning is coherent with the house-brand identity.
    3. Co-manufacturer audit registry — quality_assurance and
       co_manufacturer are free-text; production requires a structured
       vendor-audit registry with last-audit date, capacity, and recall
       readiness so a stale audit cannot pass undetected.
    4. Category-margin model — category_margin is free-text; production
       requires a category-margin model that accepts the substitution
       matrix and returns total-category-margin delta, not a narrated
       estimate.
    5. Merchandising + brand sign-off gate — a private-label SKU cannot
       launch on AI output alone; the workflow returns a recommendation
       that must be reviewed by category management, brand, and QA
       leadership before any commitment is made.
    6. Dedicated third-model cannibalization auditor — this workflow
       folds cannibalization checking into the same reviewer that
       scores recommendation quality. Production should run a
       separately configured model (different family from BOTH executor
       and reviewer) whose only job is cannibalization verification
       against the structured substitution matrix. See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import extract_flags, sanitize_for_prompt
from ...core.workflow import BaseWorkflow, WorkflowResult

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated private-label recommendation "
    "is not a launch decision. Category management, brand, and quality-"
    "assurance leadership must verify the cannibalization math, brand "
    "fit, and supply readiness before any co-manufacturer commitment "
    "or shelf-set change. AI output must never trigger an automated "
    "PO or shelf-set update."
)

_PRIVATE_LABEL_REVIEW_CRITERIA = """\
Evaluate this private-label recommendation on five dimensions. Score
each 0–10.

1. CANNIBALIZATION INTEGRITY (30%) — CRITICAL
   Does the recommendation account for substitution from the national-
   brand baseline AND adjacent SKUs in the same category? Does TOTAL
   category margin (incremental private-label margin minus lost
   national-brand margin) come out positive given cannibalization_
   estimate? Flag every shortfall under CANNIBALIZATION FLAGS:.

2. BRAND FIT (25%) — CRITICAL
   Does the proposed positioning in brand_positioning cohere with the
   house-brand identity (premium / value / specialty / good-better-
   best tier)? Does quality_assurance close the QA gap — testing
   protocol, recall readiness, regulatory compliance? Flag every
   misfit or QA gap under BRAND FLAGS:.

3. SUPPLY READINESS (20%) — CRITICAL
   Is co_manufacturer audited within an acceptable window (default:
   last 18 months)? Is stated capacity sufficient at launch volume
   AND scale-up volume? Flag every audit or capacity issue under
   SUPPLY FLAGS:.

4. PRICING DEFENSIBILITY (15%)
   Given target_cost and category_margin, is target_price achievable
   without consuming all retailer-side margin? Excessive ambiguity
   on the cost stack is a quality issue.

5. ACTIONABILITY (10%)
   Is the recommendation specific: SKU launch sequence, distribution
   footprint, shelf placement, price ladder, success metric, kill
   criteria?

Overall score = weighted average.
Score ≥ 7.5 AND zero CANNIBALIZATION / BRAND / SUPPLY flags:
recommendation is ready for category-management + brand + QA review.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  CANNIBALIZATION FLAGS: [bullet list, or "None detected"]
  BRAND FLAGS: [bullet list, or "None detected"]
  SUPPLY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are drafting a private-label launch recommendation for human
category-management, brand, and quality-assurance leadership to review.
You have no launch-velocity incentive — your job is honest
cannibalization math, honest brand-fit assessment, and honest supply-
readiness verification.

BASE EVERY CANNIBALIZATION CLAIM ON THE INPUTS. Do not import a default
substitution rate ("private-label captures ~30%") not present in
cannibalization_estimate.

BASE EVERY CAPACITY CLAIM ON THE INPUTS. If co_manufacturer capacity is
unstated, say so — do not assume it.

PRIVATE-LABEL REQUEST:
{request_text}

{wiki_context}

Produce a structured recommendation with exactly these sections:

## Cannibalization Math
Restate cannibalization_estimate plainly. Compute incremental private-
label margin vs lost margin on the national-brand baseline AND every
adjacent SKU named. State the total-category-margin delta. State the
adverse case (highest plausible substitution rate from inputs).

## Brand Fit
Walk brand_positioning against the house-brand identity. Where on the
good-better-best ladder does the SKU sit? Are there positioning
contradictions (e.g. premium positioning at a value price) that would
confuse the consumer?

## Supply Readiness
Co-manufacturer audit status: date, scope, findings if known. Stated
capacity vs launch + scale-up volume. Recall-readiness protocol.

## Pricing + Margin Stack
target_price → retailer margin → category_margin contribution.
target_cost → co-manufacturer landed cost → COGS components if known.

## Launch Plan
SKU launch sequence (single-SKU pilot vs full ladder), distribution
footprint, shelf placement vs national-brand baseline, price-ladder
disclosure to the consumer.

## Success Metric + Kill Criteria
Metric: total-category-margin delta positive at p50 substitution after
6 weeks. Kill: any QA finding, any co-manufacturer capacity miss, or
total-category-margin delta negative at adverse substitution.

## Evidence Gaps
Information missing from the inputs that materially affects
cannibalization, brand fit, or supply readiness.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this private-label recommendation. Address EVERY issue in the
reviewer's critique, especially any CANNIBALIZATION / BRAND / SUPPLY
flags.

PREVIOUS RECOMMENDATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any CANNIBALIZATION FLAG: re-do the total-category-margin math
using the substitution rates the inputs actually support; if the
adverse case is negative, narrow the launch or kill.
⚠️  For any BRAND FLAG: re-anchor positioning in the house-brand
identity; if a QA gap exists, name the closing-action.
⚠️  For any SUPPLY FLAG: name the co-manufacturer-audit refresh or
capacity-validation step that must precede launch.
"""


@dataclass
class PrivateLabelRequest:
    """Structured input for the private-label workflow."""

    proposed_sku: str
    """Proposed private-label SKU: name + category + positioning summary."""

    target_price: str
    """Target shelf price (with currency)."""

    target_cost: str
    """Target landed cost from the co-manufacturer."""

    national_brand_baseline: str
    """Incumbent national-brand SKU, share, price."""

    category_margin: str
    """Current category-margin mix."""

    cannibalization_estimate: str
    """Substitution-rate estimate from each adjacent SKU."""

    brand_positioning: str
    """House-brand identity fit (good / better / best, premium / value / specialty)."""

    quality_assurance: str
    """Testing protocol, recall readiness, regulatory compliance status."""

    co_manufacturer: str
    """Co-manufacturer vendor + audit status + stated capacity."""

    def to_prompt_text(self) -> str:
        return "\n".join([
            f"Proposed SKU: {self.proposed_sku}",
            f"Target price: {self.target_price}",
            f"Target cost: {self.target_cost}",
            f"National-brand baseline: {self.national_brand_baseline}",
            f"Category margin: {self.category_margin}",
            f"Cannibalization estimate: {self.cannibalization_estimate}",
            f"Brand positioning: {self.brand_positioning}",
            f"Quality assurance: {self.quality_assurance}",
            f"Co-manufacturer: {self.co_manufacturer}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "CANNIBALIZATION FLAGS:",
    "BRAND FLAGS:",
    "SUPPLY FLAGS:",
)


class PrivateLabelWorkflow(BaseWorkflow):
    """
    Adversarial private-label launch design: executor drafts launch
    recommendation → reviewer challenges cannibalization math, brand
    fit, and supply readiness → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero CANNIBALIZATION FLAGS
        AND zero BRAND FLAGS
        AND zero SUPPLY FLAGS
    """

    async def run(  # type: ignore[override]
        self,
        request: PrivateLabelRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial private-label launch loop."""
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
                criteria=_PRIVATE_LABEL_REVIEW_CRITERIA,
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

        approver_checklist = self._build_approver_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "proposed_sku": request.proposed_sku,
                "cannibalization_flags": list(
                    dict.fromkeys(accumulated["CANNIBALIZATION FLAGS:"])
                ),
                "brand_flags": list(dict.fromkeys(accumulated["BRAND FLAGS:"])),
                "supply_flags": list(dict.fromkeys(accumulated["SUPPLY FLAGS:"])),
                "approver_checklist": approver_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "CANNIBALIZATION FLAGS:": (
                "⚠️  CANNIBALIZATION FLAGS (re-do total-category-margin math using "
                "the substitution rates the inputs actually support; if adverse "
                "case is negative, narrow launch or kill):"
            ),
            "BRAND FLAGS:": (
                "⚠️  BRAND FLAGS (re-anchor positioning in the house-brand "
                "identity; name the closing-action for any QA gap):"
            ),
            "SUPPLY FLAGS:": (
                "⚠️  SUPPLY FLAGS (name the audit refresh or capacity-validation "
                "step that must precede launch):"
            ),
        }
        parts: list[str] = []
        for header in _FLAG_HEADERS:
            items = current[header]
            if not items:
                continue
            flags_text = "\n".join(f"  - {f}" for f in items)
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _build_approver_checklist(
        request: PrivateLabelRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["CANNIBALIZATION FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  CANNIBALIZATION FLAGS DETECTED "
                f"({len(accumulated['CANNIBALIZATION FLAGS:'])}) — category "
                "management must re-validate total-category-margin against the "
                "household-basket substitution model before any launch commitment"
            )
        if accumulated["BRAND FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  BRAND FLAGS DETECTED ({len(accumulated['BRAND FLAGS:'])}) — "
                "brand leadership must re-anchor positioning against the house-brand "
                "identity OR name the QA closing-action"
            )
        if accumulated["SUPPLY FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  SUPPLY FLAGS DETECTED ({len(accumulated['SUPPLY FLAGS:'])}) — "
                "sourcing + QA must refresh co-manufacturer audit and validate "
                "capacity at launch + scale-up volume before any commitment"
            )
        checklist.extend([
            f"[ ] Category-management review of cannibalization math for {request.proposed_sku}",
            "[ ] Brand leadership sign-off: positioning coheres with house-brand identity",
            "[ ] QA sign-off: testing protocol + recall readiness + regulatory compliance",
            "[ ] Sourcing sign-off: co-manufacturer audit current AND capacity proven",
            "[ ] No co-manufacturer commitment or shelf-set update without human review",
        ])
        return checklist
