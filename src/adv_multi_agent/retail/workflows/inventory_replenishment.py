"""
Workflow — Inventory Replenishment (Retail Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for inventory
replenishment decisions. Executor drafts a per-DC / per-SKU order
schedule from a demand forecast; reviewer (recommended: different model
family per ARIS §2.1 principle 1) challenges lead-time realism, stockout
projection, and DC / supplier capacity.

Distinct from `DemandForecastWorkflow`: demand produces a unit forecast;
replenishment turns the forecast into a per-DC / per-store order schedule
across SKUs.

Triple flag gate: LEAD-TIME FLAGS (order quantity ignores stated lead
time or assumes future lead-time improvement) + STOCKOUT FLAGS (projected
on-hand drops below safety stock during the planning window) + CAPACITY
FLAGS (order pattern exceeds DC capacity or supplier MOQ / case-pack /
ship-day windows).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Live demand-forecast feed — demand_forecast is free-text;
       production should consume a structured forecast (per-SKU per-week
       point estimate + confidence band) from `DemandForecastWorkflow`
       or an external forecast service, not a narrated paragraph.
    2. Live on-hand / on-order inventory state — sku_list is caller-
       supplied; production requires a real-time inventory feed (WMS /
       ERP) with reconciliation against in-transit POs.
    3. Supplier lead-time history — lead_times is caller-supplied;
       production should resolve against a structured supplier
       performance feed (mean + p90 actual lead time per ship-from
       location) rather than the supplier-quoted lead time alone.
    4. DC capacity model — dc_capacity is free-text; production
       requires a calibrated capacity model (pallet positions, labour
       hours per receiving window, cross-dock vs put-away mix).
    5. Truck-economics solver — truck_economics is narrated; production
       should run a transport optimiser over the actual rate cards and
       pickup windows; this workflow only sanity-checks the narrated
       trade-off.
    6. Supply-planning sign-off gate — replenishment cannot trigger
       automatically; the workflow output is a recommended schedule
       that must be reviewed by the supply-planning lead before any
       PO is cut.
    7. Dedicated third-model stockout auditor — this workflow folds
       stockout-projection checking into the same reviewer that scores
       schedule quality. Production should run a separately configured
       model (different family from BOTH executor and reviewer) whose
       only job is stockout-projection verification against the
       structured forecast feed. See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import extract_flags, sanitize_for_prompt
from ...core.workflow import BaseWorkflow, WorkflowResult

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated replenishment schedule is not "
    "a purchase order. A supply-planning lead must verify the lead-time "
    "realism, stockout projection, and DC + supplier capacity before any "
    "PO is cut. AI output must never trigger an automated PO."
)

_REPLEN_REVIEW_CRITERIA = """\
Evaluate this replenishment schedule on five dimensions. Score each 0–10.

1. LEAD-TIME REALISM (30%) — CRITICAL
   Does the schedule respect the lead_times input for every order? Are
   no orders dated such that they would only arrive AFTER an on-hand
   stockout? Does the schedule import any optimistic lead-time
   assumption ("supplier said they could expedite") not present in the
   inputs? Flag every gap under LEAD-TIME FLAGS:.

2. STOCKOUT PROTECTION (30%) — CRITICAL
   For every SKU in sku_list, does projected on-hand stay at or above
   safety_stock_policy throughout the planning window, accounting for
   demand_forecast variability AND the stated lead time? Flag every
   projected breach under STOCKOUT FLAGS:.

3. CAPACITY FIT (20%) — CRITICAL
   Does the order pattern respect dc_capacity (pallet positions,
   receiving windows) AND supplier_constraints (MOQ, case pack, ship-
   day windows)? Flag every breach under CAPACITY FLAGS:.

4. ECONOMICS (15%)
   Does the order pattern hit a defensible spot on the truck_economics
   curve (full-truck vs LTL break-even)? Excessively fragmented orders
   are a quality issue.

5. ACTIONABILITY (5%)
   Is the schedule specific: per-SKU per-order quantity, PO date, ship
   date, expected receive date, allocation to downstream stores if
   applicable?

Overall score = weighted average.
Score ≥ 7.5 AND zero LEAD-TIME / STOCKOUT / CAPACITY flags: schedule is
ready for supply-planning review. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  LEAD-TIME FLAGS: [bullet list, or "None detected"]
  STOCKOUT FLAGS: [bullet list, or "None detected"]
  CAPACITY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are drafting a per-SKU replenishment schedule for a human supply-
planning lead to review. You have no fill-rate incentive — your job is
honest lead-time application, honest stockout projection, and honest
capacity respect.

BASE EVERY ORDER DATE ON THE INPUTS. Do not import an optimistic lead
time ("supplier can usually expedite") not present in lead_times.

REPLENISHMENT REQUEST:
{request_text}

{wiki_context}

Produce a structured replenishment schedule with exactly these sections:

## Forecast Consumption
Restate the demand_forecast in your own terms: per-SKU per-week point
estimate AND confidence band. If the forecast is missing variability,
state the adverse case explicitly.

## Per-SKU Schedule
For every SKU in sku_list, a table-like block:
  SKU | Current on-hand | On-order | Safety stock | PO 1 (qty, ship, recv) | PO 2 ...
PO dates must respect lead_times for the relevant supplier.

## Stockout Projection
For every SKU, walk the projected on-hand week-by-week through the
planning window, against safety_stock_policy. Identify the lowest point
and the week it occurs. State plainly any week where projected on-hand
breaches safety stock.

## Capacity Check
DC pallet-positions consumed by the schedule vs dc_capacity. Supplier
MOQ / case-pack / ship-day adherence per supplier_constraints.

## Truck Economics
For each PO, full-truck vs LTL classification given truck_economics.
Identify fragmentation that lifts cost without service benefit.

## Success Metric + Kill Criteria
Metric: schedule meets safety_stock_policy at all SKU-weeks. Kill: any
projected breach inside the lead-time horizon — escalate to expedite
review.

## Evidence Gaps
Information missing from the inputs that materially affects lead-time
realism, stockout projection, or capacity fit.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this replenishment schedule. Address EVERY issue in the
reviewer's critique, especially any LEAD-TIME / STOCKOUT / CAPACITY
flags.

PREVIOUS SCHEDULE:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any LEAD-TIME FLAG: re-anchor PO dates in lead_times; if a
quoted lead time cannot be met, escalate to expedite review explicitly.
⚠️  For any STOCKOUT FLAG: pull forward the next PO, increase order
quantity to the next case-pack tier, or escalate to expedite.
⚠️  For any CAPACITY FLAG: re-stage orders against dc_capacity / supplier
MOQ; do NOT assume capacity creates itself.
"""


@dataclass
class InventoryReplenishmentRequest:
    """Structured input for the replenishment workflow."""

    dc_id: str
    """Distribution center identifier."""

    sku_list: str
    """SKUs in scope with current on-hand + on-order."""

    demand_forecast: str
    """Per-SKU per-week forecast (point + band). Accepts narrated `DemandForecastWorkflow`
    output or external forecast."""

    lead_times: str
    """Per-supplier lead times (quoted, with any history if available)."""

    safety_stock_policy: str
    """Corporate safety-stock rule (e.g. 1.5σ over lead time)."""

    dc_capacity: str
    """DC physical / labour constraint (pallet positions, receiving windows)."""

    truck_economics: str
    """Full-truck vs LTL break-even context."""

    supplier_constraints: str
    """MOQ, case pack, ship-day windows per supplier."""

    def to_prompt_text(self) -> str:
        return "\n".join([
            f"DC: {self.dc_id}",
            f"SKU list (on-hand + on-order): {self.sku_list}",
            f"Demand forecast: {self.demand_forecast}",
            f"Lead times: {self.lead_times}",
            f"Safety stock policy: {self.safety_stock_policy}",
            f"DC capacity: {self.dc_capacity}",
            f"Truck economics: {self.truck_economics}",
            f"Supplier constraints: {self.supplier_constraints}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "LEAD-TIME FLAGS:",
    "STOCKOUT FLAGS:",
    "CAPACITY FLAGS:",
)


class InventoryReplenishmentWorkflow(BaseWorkflow):
    """
    Adversarial replenishment-schedule design: executor drafts per-SKU
    PO schedule → reviewer challenges lead-time realism, stockout
    projection, and capacity fit → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero LEAD-TIME FLAGS
        AND zero STOCKOUT FLAGS
        AND zero CAPACITY FLAGS
    """

    async def run(  # type: ignore[override]
        self,
        request: InventoryReplenishmentRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial replenishment-schedule loop."""
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
                criteria=_REPLEN_REVIEW_CRITERIA,
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
                "dc_id": request.dc_id,
                "lead_time_flags": list(dict.fromkeys(accumulated["LEAD-TIME FLAGS:"])),
                "stockout_flags": list(dict.fromkeys(accumulated["STOCKOUT FLAGS:"])),
                "capacity_flags": list(dict.fromkeys(accumulated["CAPACITY FLAGS:"])),
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
            "LEAD-TIME FLAGS:": (
                "⚠️  LEAD-TIME FLAGS (re-anchor PO dates in lead_times, or escalate "
                "to expedite review):"
            ),
            "STOCKOUT FLAGS:": (
                "⚠️  STOCKOUT FLAGS (pull forward PO, increase order quantity, or "
                "escalate to expedite):"
            ),
            "CAPACITY FLAGS:": (
                "⚠️  CAPACITY FLAGS (re-stage against DC capacity / supplier MOQ; do "
                "NOT assume capacity creates itself):"
            ),
        }
        parts: list[str] = []
        for header in _FLAG_HEADERS:
            items = current[header]
            if not items:
                continue
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}" for f in items
            )
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _build_approver_checklist(
        request: InventoryReplenishmentRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["LEAD-TIME FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  LEAD-TIME FLAGS DETECTED "
                f"({len(accumulated['LEAD-TIME FLAGS:'])}) — supply-planning lead "
                "must re-anchor PO dates in supplier-quoted lead times before any "
                "PO is cut"
            )
        if accumulated["STOCKOUT FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  STOCKOUT FLAGS DETECTED "
                f"({len(accumulated['STOCKOUT FLAGS:'])}) — expedite review required "
                "for every SKU-week with a projected safety-stock breach"
            )
        if accumulated["CAPACITY FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  CAPACITY FLAGS DETECTED "
                f"({len(accumulated['CAPACITY FLAGS:'])}) — DC operations + sourcing "
                "must reconcile order pattern against capacity and supplier MOQ"
            )
        checklist.extend([
            f"[ ] Supply-planning review of stockout projection at DC {request.dc_id}",
            "[ ] DC ops sign-off: receiving windows + pallet positions reconcile",
            "[ ] Sourcing sign-off: MOQ / case-pack / ship-day adherence per supplier",
            "[ ] Transport: confirm full-truck consolidation opportunities not lost",
            "[ ] No AI-generated PO release without human review",
        ])
        return checklist
