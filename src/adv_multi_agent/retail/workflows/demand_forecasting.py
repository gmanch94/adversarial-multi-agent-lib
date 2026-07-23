"""
Workflow — Demand Forecasting (Retail Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for retail replenishment
decisions. Executor synthesizes a demand forecast; reviewer (recommended:
different model family per ARIS §2.1 principle 1) challenges assumptions
and flags any unsubstantiated adjustments under ASSUMPTION FLAGS.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Live POS data — historical_sales is free-text; production requires
       integration with store transaction systems.
    2. Actuarial demand model — ML baseline (e.g. Prophet, LightGBM) should
       underpin the forecast; LLM adjusts the residual, not the baseline.
    3. Supplier API — lead_time_days should be fetched from supplier EDI/API
       in real time, not caller-supplied text.
    4. Cost model — stockout and overstock costs should be computed from
       actual margin and spoilage data, not qualitative assessment.
    5. Buyer approval gate — the replenishment order must not be placed
       automatically. A human buyer must review and confirm.
    6. Dedicated third-model assumption auditor — this workflow folds the
       assumption audit into the same reviewer that scores quality (single-
       stage), which differs from the ARIS three-stage assurance cascade
       (experiment-audit → result-to-claim → paper-claim-audit). A
       production system should use a separately configured model (different
       family from BOTH executor and reviewer) whose only job is to flag
       unsubstantiated assumptions. See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import extract_flags, sanitize_for_prompt, truncate_flag_display
from ...core.workflow import BaseWorkflow, WorkflowResult

# L-PC-3: per-field cap on Request.to_prompt_text. Bounds any single
# free-text field so one oversized field cannot crowd out later fields
# when the concatenated prompt is trimmed by sanitize_for_prompt(max_chars=6000).
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated forecast is not a purchase order. "
    "A human buyer must review all assumptions independently and approve any "
    "replenishment action. AI output must never trigger automated ordering."
)

_FORECAST_REVIEW_CRITERIA = """\
Evaluate this demand forecast on five dimensions. Score each 0–10.

1. FORECAST GROUNDING (30%)
   Is the forecast anchored to the historical sales signal? Are week-over-week
   adjustments proportionate and direction-consistent with the stated drivers?
   Penalise forecasts that deviate from the baseline without evidence.

2. ASSUMPTION AUDIT (25%)
   Are all adjustments (seasonality, promotions, weather, events) explicitly
   stated and justified with evidence from the inputs? Flag every unsubstantiated
   assumption under ASSUMPTION FLAGS:. An assumption not present in the inputs
   is a flag even if plausible.

3. RISK BALANCE (25%)
   Does the replenishment recommendation balance stockout risk (lost sales,
   customer dissatisfaction) against overstock risk (spoilage, working capital)?
   Is the safety stock reasoning sound?

4. COMPLETENESS (10%)
   Are data gaps noted? Is forecast confidence expressed appropriately?
   Is the recommendation tied to a specific order quantity and date?

5. ACTIONABILITY (10%)
   Is the order recommendation specific enough for a buyer to act on:
   units, timing, supplier, delivery window?

Overall score = weighted average.
Score ≥ 7.5: forecast is ready for buyer review.
Score < 7.5: requires revision.

End your review with:
  Overall score: X/10
  Key issues: [bullet list]
  ASSUMPTION FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a demand forecast and replenishment recommendation for a human buyer.
You have no stake in the outcome. Your job is accuracy — not advocacy for a particular
order size.

BASE ALL ADJUSTMENTS ON THE INPUT DATA PROVIDED. Do not import assumptions from
general retail knowledge that are not grounded in the specific store, SKU, and
time-period data below.

STORE DATA:
{request_text}

{wiki_context}

Produce a structured forecast with exactly these sections:

## Demand Signal Analysis
Describe the baseline demand from historical sales. Identify trend direction,
variance, and any anomalies. State the average weekly run rate.

## Forecast
Four-week unit forecast, week by week. State each adjustment to the baseline
explicitly: driver, direction, magnitude, evidence source.

## Replenishment Recommendation
Specific: units to order, order-by date, expected delivery date (using stated
lead time), target post-delivery inventory level.

## Key Assumptions
One bullet per assumption. Each must be traceable to an input field.

## Evidence Gaps
Information missing from the inputs that would materially improve forecast
accuracy. Note the impact of each gap on confidence.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this demand forecast. Address EVERY issue in the reviewer's critique,
especially any ASSUMPTION FLAGS.

PREVIOUS FORECAST:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged assumption: REMOVE the adjustment or replace it with
evidence directly present in the input data. Do not rephrase — remove or ground it.
"""


@dataclass
class ForecastRequest:
    """Structured input for the demand forecast workflow."""

    store_id: str
    """Store identifier, e.g. 'KRO-OH-0042'."""

    sku: str
    """SKU code for the product being forecast."""

    product_category: str
    """Category, e.g. 'dairy', 'produce', 'beverages'."""

    historical_sales: str
    """Free-text: units sold per week for the last 8 weeks."""

    current_inventory: str
    """On-hand and in-transit units."""

    lead_time_days: str
    """Supplier lead time in days."""

    upcoming_events: str
    """Local events, holidays, promotions in the next 4 weeks."""

    seasonality_notes: str
    """Known seasonal patterns for this SKU or category."""

    weather_forecast: str
    """Two-week weather outlook (temperature, precipitation)."""

    unemployment_rate: str
    """Local unemployment rate and trend — used as consumer spending signal."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Store: {self.store_id[:cap]}",
            f"SKU: {self.sku[:cap]}",
            f"Category: {self.product_category[:cap]}",
            f"Historical sales (8 wk): {self.historical_sales[:cap]}",
            f"Current inventory: {self.current_inventory[:cap]}",
            f"Lead time: {self.lead_time_days[:cap]} days",
            f"Upcoming events: {self.upcoming_events[:cap]}",
            f"Seasonality: {self.seasonality_notes[:cap]}",
            f"Weather forecast: {self.weather_forecast[:cap]}",
            f"Unemployment rate: {self.unemployment_rate[:cap]}",
        ])


class DemandForecastWorkflow(BaseWorkflow):
    """
    Adversarial demand forecasting: executor drafts forecast → reviewer
    challenges assumptions → iterate.

    Convergence gate: score ≥ threshold AND zero ASSUMPTION FLAGS.
    """

    async def run(  # type: ignore[override]
        self,
        request: ForecastRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial forecast loop."""
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_flags: list[str] = []
        all_flags: list[str] = []

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    request_text=request_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                flag_section = ""
                if current_flags:
                    flags_text = "\n".join(
                        f"  - {f}" for f in truncate_flag_display(current_flags)
                    )
                    flag_section = (
                        f"\n⚠️  ASSUMPTION FLAGS (remove or ground in input data):\n"
                        f"{flags_text}\n"
                    )
                prompt = _REVISION_PROMPT.format(
                    previous=sanitize_for_prompt(output, max_chars=10000),
                    score=f"{score:.1f}",
                    critique=sanitize_for_prompt(review.critique, max_chars=4000),
                    suggestions="\n".join(
                        f"- {sanitize_for_prompt(s, max_chars=500)}"
                        for s in review.suggestions
                    ),
                    flag_section=flag_section,
                    wiki_context=wiki_ctx,
                )

            output = await self.executor.run(prompt, context="")
            self._register_claims(output, round_num)

            review = await self.reviewer.review(
                output,
                criteria=_FORECAST_REVIEW_CRITERIA,
            )
            score = review.score
            current_flags = extract_flags(review.critique, "ASSUMPTION FLAGS:")
            all_flags.extend(current_flags)

            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=config.max_wiki_body_chars),
                round_num=round_num,
                score=score,
            )

            if review.approved and not current_flags:
                converged = True
                break

        buyer_checklist = self._build_buyer_checklist(request, all_flags)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "store_id": sanitize_for_prompt(request.store_id, max_chars=200),
                "sku": sanitize_for_prompt(request.sku, max_chars=200),
                "assumption_flags": list(dict.fromkeys(all_flags)),
                "buyer_checklist": buyer_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _build_buyer_checklist(
        request: ForecastRequest,
        assumption_flags: list[str],
    ) -> list[str]:
        checklist: list[str] = []
        if assumption_flags:
            checklist.append(
                f"[ ] ⚠️  ASSUMPTION FLAGS DETECTED ({len(assumption_flags)}) — "
                "verify each flagged assumption against store data before ordering"
            )
        checklist.extend([
            f"[ ] Verify historical sales data for {request.sku} in store {request.store_id}",
            "[ ] Confirm upcoming events and promotion dates are current",
            "[ ] Cross-check weather forecast against latest NWS data",
            "[ ] Validate lead time with supplier before placing order",
            "[ ] Review forecast against category manager's weekly guidance",
            "[ ] Approve replenishment order — AI output must not trigger auto-ordering",
        ])
        return checklist
