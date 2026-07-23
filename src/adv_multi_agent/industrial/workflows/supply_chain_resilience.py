"""
Workflow — Supply Chain Resilience (Industrial Manufacturing Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to supply-chain-
resilience assessment for an industrial OEM exposed to logistics
chokepoints, single-source dependencies, and sub-tier concentration
(the "insulate the supply chain" thesis exemplified by Crown Equipment).

Executor drafts a resilience assessment; reviewer (recommended: different
model family per ARIS §2.1 principle 1) challenges optimistic
"we have a second source" claims that aren't actually dual-sourced at
the sub-tier, geographic-concentration risk hidden by Tier-1 diversity,
and lead-time fragility from common-vendor / common-route exposure.

Triple-flag gate (D-IND-1): SINGLE-SOURCE FLAGS, GEO-CONCENTRATION FLAGS,
LEAD-TIME-FRAGILITY FLAGS. **No reviewer veto** — resilience changes are
program-level and reversible.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Supply-chain visibility integration — Resilinc / Interos / Everstream
       sub-tier mapping is the authoritative source; this workflow consumes
       caller-supplied prose only.
    2. Geopolitical risk feed — country-level export-control, sanctions,
       and unrest risk should come from a structured feed, not narrative.
    3. Logistics-route resilience — common-route exposure (Panama Canal,
       Suez, Strait of Malacca, Strait of Hormuz, Polish-Belarus border)
       and modal-substitution feasibility require a structured route
       database.
    4. Single-source detection — sub-tier mapping must verify that a
       Tier-2 supplier serving multiple Tier-1s does not create hidden
       single-source exposure at the OEM level.
    5. Inventory buffer policy — strategic-buffer recommendation requires
       integration with ERP / MRP for opportunity-cost calculation.
    6. Append-only audit store + dedicated third-model auditor — see
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

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated supply-chain-resilience "
    "assessment is not an authorised sourcing change. A credentialed "
    "supply-chain council + sourcing council member must verify "
    "single-source, sub-tier, and route claims against structured "
    "visibility data before any resilience-investment decision is "
    "approved. AI output must never trigger an automated sourcing change."
)

_RESILIENCE_REVIEW_CRITERIA = """\
Evaluate this supply-chain-resilience assessment on four dimensions.
Score each 0–10.

1. SINGLE-SOURCE INTEGRITY (30%) — CRITICAL
   Does the assessment validate dual-source claims at the BOM-line level
   AND verify that Tier-2 sub-suppliers do not create hidden single-source
   exposure (one Tier-2 serving multiple Tier-1s on the same commodity)?
   Penalise "we have multiple suppliers" claims that haven't been mapped
   to sub-tier. Flag every gap under SINGLE-SOURCE FLAGS:.

2. GEOGRAPHIC CONCENTRATION (30%) — CRITICAL
   Is the geographic exposure mapped at country + region + cluster level
   (not just country)? Are export-control, sanctions, and political-risk
   overlays current? Are natural-hazard (typhoon-zone, seismic, water-
   stress) overlays applied? Penalise country-level claims that miss
   regional clustering. Flag every gap under GEO-CONCENTRATION FLAGS:.

3. LEAD-TIME FRAGILITY (25%) — CRITICAL
   Is logistics-route fragility analysed (common chokepoints, modal
   substitution, port-of-entry diversity)? Is buffer-inventory adequate
   given lead-time variability? Are critical-spare and surge-capacity
   strategies stated? Penalise narrow "lead-time = N weeks" claims that
   ignore variance and route risk. Flag every gap under LEAD-TIME-
   FRAGILITY FLAGS:.

4. ACTIONABILITY (15%)
   Are the resilience actions (dual-sourcing plan, sub-tier audit, route
   diversification, strategic-buffer policy, supplier-development invest)
   specific enough for the supply-chain council to act on with cost +
   timeline?

Overall score = weighted average.
Score ≥ 7.5 AND zero SINGLE-SOURCE FLAGS AND zero GEO-CONCENTRATION FLAGS
AND zero LEAD-TIME-FRAGILITY FLAGS: assessment is ready for supply-chain-
council review. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SINGLE-SOURCE FLAGS: [bullet list, or "None detected"]
  GEO-CONCENTRATION FLAGS: [bullet list, or "None detected"]
  LEAD-TIME-FRAGILITY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a supply-chain-resilience assessment for an industrial
OEM's supply-chain council. You have no stake in the outcome. Your job
is to identify resilience exposures and propose actions defensible against
sub-tier visibility data — not to assume Tier-1 diversity is enough, not
to overstate exposure for cautious defaults.

BASE THE ASSESSMENT ON THE INPUT DATA.

SUPPLY-CHAIN DATA:
{request_text}

{wiki_context}

Produce a structured assessment with exactly these sections:

## Commodity Summary
Restate the commodity / sub-system, annual spend, criticality classification,
and the OEM's current sourcing posture (sole / single / dual / multi).

## Single-Source Analysis
For each BOM line: dual-source status at Tier-1 AND Tier-2. Flag hidden
single-source exposure where multiple Tier-1s share a Tier-2 sub-supplier.

## Geographic Concentration
Country + region + cluster mapping of Tier-1 and Tier-2. Export-control,
sanctions, political-risk overlay. Natural-hazard (typhoon / seismic /
water-stress) overlay.

## Lead-Time and Route Fragility
Lead-time central tendency + variance. Common-route exposure (Panama,
Suez, Malacca, Hormuz, single-port). Modal-substitution feasibility.

## Inventory and Buffer Posture
Current strategic-buffer policy, critical-spare strategy, surge-capacity
reservation.

## Resilience Action Plan
Dual-sourcing initiation, sub-tier audit, route diversification, buffer-
policy update, supplier-development invest. Each action: owner, cost,
timeline, success criterion.

## Evidence Gaps
Information missing from the inputs that materially affects the
assessment.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this supply-chain-resilience assessment. Address EVERY issue in
the reviewer's critique, especially any SINGLE-SOURCE FLAGS,
GEO-CONCENTRATION FLAGS, or LEAD-TIME-FRAGILITY FLAGS.

PREVIOUS ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SINGLE-SOURCE FLAG: map sub-tier exposure or downgrade the
dual-source claim.
⚠️  For any GEO-CONCENTRATION FLAG: refine to region / cluster level and
add the natural-hazard or political-risk overlay.
⚠️  For any LEAD-TIME-FRAGILITY FLAG: state lead-time variance, route
exposure, and the buffer-policy implication.
"""


@dataclass
class SupplyChainResilienceRequest:
    """Structured input for the supply-chain-resilience workflow."""

    commodity_summary: str
    """Commodity / sub-system, annual spend, criticality classification,
    current sourcing posture."""

    tier1_supplier_map: str
    """Tier-1 supplier list with location, share, dual/single status."""

    tier2_visibility: str
    """Tier-2 sub-supplier mapping where known; gaps explicit."""

    geographic_context: str
    """Country / region / cluster overlay + political-risk + natural-hazard."""

    lead_time_and_route_context: str
    """Lead-time mean + variance; logistics-route exposure; modal alternatives."""

    inventory_and_buffer: str
    """Strategic-buffer policy, critical-spare strategy, surge capacity."""

    incident_or_trigger: str
    """Recent disruption / regulator change / supplier alert that prompts
    the resilience review."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Commodity summary: {self.commodity_summary[:cap]}",
            f"Tier-1 supplier map: {self.tier1_supplier_map[:cap]}",
            f"Tier-2 visibility: {self.tier2_visibility[:cap]}",
            f"Geographic context: {self.geographic_context[:cap]}",
            f"Lead-time and route context: {self.lead_time_and_route_context[:cap]}",
            f"Inventory and buffer: {self.inventory_and_buffer[:cap]}",
            f"Incident or trigger: {self.incident_or_trigger[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "SINGLE-SOURCE FLAGS:",
    "GEO-CONCENTRATION FLAGS:",
    "LEAD-TIME-FRAGILITY FLAGS:",
)


class SupplyChainResilienceWorkflow(BaseWorkflow):
    """
    Adversarial supply-chain-resilience review: executor drafts an
    assessment → reviewer challenges Tier-1-only dual-source claims,
    region-level geographic clustering, and lead-time route fragility →
    iterate.

    Convergence gate (D-IND-1):
        score ≥ threshold
        AND zero SINGLE-SOURCE FLAGS
        AND zero GEO-CONCENTRATION FLAGS
        AND zero LEAD-TIME-FRAGILITY FLAGS

    No reviewer veto — resilience-investment decisions are program-level
    and reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: SupplyChainResilienceRequest,
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
                criteria=_RESILIENCE_REVIEW_CRITERIA,
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
                "commodity_summary": sanitize_for_prompt(
                    request.commodity_summary, max_chars=200
                ),
                "single_source_flags": list(
                    dict.fromkeys(accumulated["SINGLE-SOURCE FLAGS:"])
                ),
                "geo_concentration_flags": list(
                    dict.fromkeys(accumulated["GEO-CONCENTRATION FLAGS:"])
                ),
                "lead_time_fragility_flags": list(
                    dict.fromkeys(accumulated["LEAD-TIME-FRAGILITY FLAGS:"])
                ),
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
            "SINGLE-SOURCE FLAGS:": (
                "⚠️  SINGLE-SOURCE FLAGS (map sub-tier exposure or downgrade "
                "the dual-source claim):"
            ),
            "GEO-CONCENTRATION FLAGS:": (
                "⚠️  GEO-CONCENTRATION FLAGS (refine to region / cluster + "
                "add natural-hazard or political-risk overlay):"
            ),
            "LEAD-TIME-FRAGILITY FLAGS:": (
                "⚠️  LEAD-TIME-FRAGILITY FLAGS (state lead-time variance, "
                "route exposure, buffer-policy implication):"
            ),
        }
        parts: list[str] = []
        for header in _FLAG_HEADERS:
            flags = current[header]
            if not flags:
                continue
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(flags)
            )
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _build_approver_checklist(
        request: SupplyChainResilienceRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["SINGLE-SOURCE FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  SINGLE-SOURCE FLAGS "
                f"({len(accumulated['SINGLE-SOURCE FLAGS:'])}) — "
                "map sub-tier; validate Tier-2 distinctness"
            )
        if accumulated["GEO-CONCENTRATION FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  GEO-CONCENTRATION FLAGS "
                f"({len(accumulated['GEO-CONCENTRATION FLAGS:'])}) — "
                "refine to region/cluster; refresh political-risk overlay"
            )
        if accumulated["LEAD-TIME-FRAGILITY FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  LEAD-TIME-FRAGILITY FLAGS "
                f"({len(accumulated['LEAD-TIME-FRAGILITY FLAGS:'])}) — "
                "quantify variance; assess route-substitution feasibility"
            )
        checklist.extend([
            "[ ] Supply-chain council sign-off on resilience-investment ask",
            "[ ] Sourcing council confirmation of dual-source / regional-shift plan",
            "[ ] Finance: buffer-inventory opportunity-cost reconciliation",
            "[ ] Sub-tier audit prioritisation per concentration ranking",
            f"[ ] Re-evaluate trigger context: {request.incident_or_trigger[:60]}",
            "[ ] Approve resilience program — AI output must not trigger automatic invest",
        ])
        return checklist
