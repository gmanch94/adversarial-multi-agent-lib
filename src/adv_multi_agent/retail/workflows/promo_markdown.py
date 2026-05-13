"""
Workflow — Promo / Markdown Optimization (Retail Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for retail promo /
markdown decisions. Executor drafts a discount proposal; reviewer
(recommended: different model family per ARIS §2.1 principle 1)
challenges elasticity, margin math, and timing.

Triple flag gate: ELASTICITY FLAGS (promo depth assumes elasticity not
supported by inputs) + MARGIN FLAGS (net margin including cannibalization
drops below floor) + TIMING FLAGS (promo collides with a concurrent
campaign or major demand event without justification).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Live elasticity model — elasticity_estimate is free-text; production
       requires a category-level elasticity surface from a price-test
       history or a structured econometric model, not an LLM-paraphrased
       benchmark.
    2. Cannibalization graph — cannibalization_risk is free-text; production
       requires a household-basket co-occurrence model so substitution
       cost can be computed per affected SKU, not narrated.
    3. Competitor pricing feed — competitor_pricing is caller-supplied;
       production requires a price-scrape or syndicated competitive feed
       with timestamps.
    4. Category manager + finance sign-off gate — promo cannot trigger
       automatically; the workflow output is a recommendation, not an
       authorisation.
    5. Dedicated third-model elasticity auditor — this workflow folds
       elasticity checking into the same reviewer that scores quality.
       Production should run a separately configured model (different
       family from BOTH executor and reviewer) whose only job is
       elasticity-claim verification against a structured benchmark.
       See ARIS §3.1.
    6. Markdown-cascade audit — promo decisions cascade into successor
       markdowns and clearance schedules. This workflow scopes one
       promo at a time; a sweep audit (multi-week cascade) is out of
       scope.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import extract_flags, sanitize_for_prompt
from ...core.workflow import BaseWorkflow, WorkflowResult

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated promo plan is not a published "
    "campaign. A category manager and finance partner must verify the "
    "elasticity assumption, margin math, and timing alignment before any "
    "price change goes live. AI output must never trigger an automated "
    "price update."
)

_PROMO_REVIEW_CRITERIA = """\
Evaluate this promo plan on five dimensions. Score each 0–10.

1. ELASTICITY GROUNDING (30%) — CRITICAL
   Is the assumed price elasticity directly supported by the
   elasticity_estimate input (category benchmark, prior price-test, or
   structured econometric source)? Flag every elasticity claim that
   extrapolates beyond the supplied range, or imports a default elasticity
   not present in the inputs. Surface under ELASTICITY FLAGS:.

2. MARGIN INTEGRITY (25%) — CRITICAL
   Does the net contribution margin INCLUDING expected cannibalization on
   the SKUs named in cannibalization_risk stay at or above margin_floor?
   Account for: discount depth, expected substitution rate, free-rider
   redemption, fulfilment cost lift if applicable. Flag every shortfall
   under MARGIN FLAGS:.

3. TIMING FIT (20%)
   Does the promo_window collide with a concurrent campaign (internal),
   a competitor event (external), or a major demand event in a way that
   would distort the read of the promo's incremental lift? Flag under
   TIMING FLAGS:.

4. COMPETITIVE COHERENCE (15%)
   Is the proposed depth coherent given competitor_pricing — neither so
   shallow that it fails to drive traffic, nor so deep that it triggers a
   competitor response without margin headroom to absorb one?

5. ACTIONABILITY (10%)
   Is the promo specific: mechanic, depth, exclusions, channels,
   start/end times, success metric, kill criteria?

Overall score = weighted average.
Score ≥ 7.5 AND zero ELASTICITY / MARGIN / TIMING flags: promo is ready
for category-manager + finance review. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  ELASTICITY FLAGS: [bullet list, or "None detected"]
  MARGIN FLAGS: [bullet list, or "None detected"]
  TIMING FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are designing a promo / markdown plan for a human category manager
and finance partner to review. You have no sell-through incentive —
your job is honest elasticity, honest margin math, and honest timing.

BASE EVERY ELASTICITY ASSUMPTION ON THE INPUTS. Do not import a default
elasticity ("retail is ~-1.5") that is not present in the
elasticity_estimate field.

PROMO REQUEST:
{request_text}

{wiki_context}

Produce a structured promo plan with exactly these sections:

## Elasticity Assumption
State the elasticity figure you will use, and which input field supports
it. Note the confidence band (e.g. "category-level benchmark, ±0.3").
If the input is insufficient, say so — do not import a default.

## Promo Mechanic
Mechanic (price cut / BOGO / threshold), depth (state both % and $),
exclusions, channels (in-store / curbside / digital), start/end times.

## Expected Lift
Projected unit-volume lift using the stated elasticity. Project both
the central estimate and an adverse case at the lower confidence bound.

## Margin Math
For both the central and adverse cases:
  - Discount cost per redemption
  - Cannibalization cost (lost margin on substituted SKUs from
    cannibalization_risk)
  - Free-rider cost
  - Fulfilment cost lift (if channel-specific)
  - Net per-unit margin vs floor

## Timing Risk
Identify every concurrent / adjacent event named in competing inputs.
For each, state the distortion to the lift read AND the mitigation
(reweight, shift, or accept).

## Success Metric + Kill Criteria
Metric for promo success. Threshold or window that triggers early kill.

## Evidence Gaps
Information missing from the inputs that materially affects elasticity
or margin reads.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this promo plan. Address EVERY issue in the reviewer's critique,
especially any ELASTICITY / MARGIN / TIMING flags.

PREVIOUS PROMO:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any ELASTICITY FLAG: tighten the elasticity claim to what the
inputs actually support, or narrow the promo depth.
⚠️  For any MARGIN FLAG: re-do the margin math; if the adverse-case
floor cannot be held, narrow depth or kill the promo.
⚠️  For any TIMING FLAG: shift the promo_window, accept the distortion
with a stated mitigation, or kill.
"""


@dataclass
class PromoRequest:
    """Structured input for the promo / markdown workflow."""

    sku: str
    """SKU code for the item being promoted."""

    category: str
    """Category, e.g. 'beverages', 'dairy', 'health-and-beauty'."""

    current_price: str
    """Current shelf price (with currency)."""

    inventory_on_hand: str
    """On-hand inventory and weeks-of-supply context."""

    weeks_of_supply: str
    """Forward weeks-of-supply at current run rate."""

    competitor_pricing: str
    """Competitor price points for the same / substitute SKU."""

    elasticity_estimate: str
    """Elasticity figure with source: category benchmark, prior price test,
    structured econometric estimate."""

    margin_floor: str
    """Minimum acceptable per-unit margin (with unit)."""

    promo_window: str
    """Planned start + end dates / hours."""

    cannibalization_risk: str
    """Adjacent SKUs likely to absorb demand, with approximate substitution
    magnitude if known."""

    def to_prompt_text(self) -> str:
        return "\n".join([
            f"SKU: {self.sku}",
            f"Category: {self.category}",
            f"Current price: {self.current_price}",
            f"Inventory on hand: {self.inventory_on_hand}",
            f"Weeks of supply: {self.weeks_of_supply}",
            f"Competitor pricing: {self.competitor_pricing}",
            f"Elasticity estimate: {self.elasticity_estimate}",
            f"Margin floor: {self.margin_floor}",
            f"Promo window: {self.promo_window}",
            f"Cannibalization risk: {self.cannibalization_risk}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "ELASTICITY FLAGS:",
    "MARGIN FLAGS:",
    "TIMING FLAGS:",
)


class PromoMarkdownWorkflow(BaseWorkflow):
    """
    Adversarial promo / markdown design: executor drafts depth + window →
    reviewer challenges elasticity, margin, and timing → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero ELASTICITY FLAGS
        AND zero MARGIN FLAGS
        AND zero TIMING FLAGS
    """

    async def run(  # type: ignore[override]
        self,
        request: PromoRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial promo-design loop."""
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
                criteria=_PROMO_REVIEW_CRITERIA,
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
                "sku": request.sku,
                "category": request.category,
                "elasticity_flags": list(dict.fromkeys(accumulated["ELASTICITY FLAGS:"])),
                "margin_flags": list(dict.fromkeys(accumulated["MARGIN FLAGS:"])),
                "timing_flags": list(dict.fromkeys(accumulated["TIMING FLAGS:"])),
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
            "ELASTICITY FLAGS:": (
                "⚠️  ELASTICITY FLAGS (tighten claim to what the inputs support, or "
                "narrow promo depth):"
            ),
            "MARGIN FLAGS:": (
                "⚠️  MARGIN FLAGS (re-do margin math; if adverse-case floor cannot be "
                "held, narrow depth or kill):"
            ),
            "TIMING FLAGS:": (
                "⚠️  TIMING FLAGS (shift window, state mitigation, or kill):"
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
        request: PromoRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["ELASTICITY FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  ELASTICITY FLAGS DETECTED "
                f"({len(accumulated['ELASTICITY FLAGS:'])}) — category manager must "
                "validate elasticity claim against price-test history before promo go-live"
            )
        if accumulated["MARGIN FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  MARGIN FLAGS DETECTED ({len(accumulated['MARGIN FLAGS:'])}) — "
                "finance must reconfirm adverse-case net margin against the floor"
            )
        if accumulated["TIMING FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  TIMING FLAGS DETECTED ({len(accumulated['TIMING FLAGS:'])}) — "
                "marketing ops must reconcile against the campaign calendar"
            )
        checklist.extend([
            f"[ ] Category-manager review of elasticity claim for SKU {request.sku}",
            f"[ ] Finance sign-off: adverse-case margin ≥ stated floor ({request.margin_floor})",
            "[ ] Marketing ops: confirm no concurrent campaign distorts the lift read",
            "[ ] POS / pricing-engine update — manual review BEFORE schedule activation",
            "[ ] Kill-criteria + monitoring window committed to operational runbook",
        ])
        return checklist
