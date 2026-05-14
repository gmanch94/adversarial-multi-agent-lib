"""
Workflow — Supplier Negotiation Briefs (Retail Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for supplier
negotiation prep. Executor drafts a negotiation brief; reviewer
(recommended: different model family per ARIS §2.1 principle 1)
challenges the BATNA, cost floor, and relationship implications.

Triple flag gate: BATNA FLAGS (no defensible alternative supplier
identified, or alternatives hand-waved) + COST FLAGS (buyer asks below
defensible cost floor implied by cost_drivers) + RELATIONSHIP FLAGS
(proposed tactic damages a strategic supplier relationship without
explicit acknowledgement).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Live cost-driver index — cost_drivers is free-text; production
       requires a structured input-cost feed (commodity indices, freight
       benchmarks, FX where relevant) so cost-floor claims can be
       reproduced, not narrated.
    2. Alternative-supplier qualification model — alternatives is
       caller-supplied free-text; production requires a vetted backup-
       supplier registry with capacity, audit status, and quoted unit
       cost so BATNA strength is auditable.
    3. Strategic-relationship classification — relationship_context is
       caller-supplied; production should pull from a category-level
       supplier-tier map (strategic / preferred / commodity) with the
       commercial implications of each tier already encoded.
    4. Procurement + legal sign-off gate — negotiation cannot proceed on
       AI output alone; the workflow returns a recommendation that must
       be reviewed by the category buyer, finance, and legal before any
       proposal is sent to the supplier.
    5. Dedicated third-model cost-floor auditor — this workflow folds
       cost-floor checking into the same reviewer that scores brief
       quality. Production should run a separately configured model
       (different family from BOTH executor and reviewer) whose only
       job is cost-floor verification against the structured cost-driver
       feed. See ARIS §3.1.
    6. ESG / compliance constraint registry — negotiation_constraints
       captures corporate ESG / compliance rules; production should
       resolve these against a structured policy registry rather than a
       narrated paragraph.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import extract_flags, sanitize_for_prompt
from ...core.workflow import BaseWorkflow, WorkflowResult

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated negotiation brief is not a "
    "supplier proposal. A category buyer, finance partner, and legal "
    "reviewer must verify the BATNA, cost floor, and relationship "
    "implications before any term is communicated to the supplier. "
    "AI output must never be sent to a supplier without human sign-off."
)

_BRIEF_REVIEW_CRITERIA = """\
Evaluate this supplier negotiation brief on five dimensions. Score each 0–10.

1. BATNA STRENGTH (30%) — CRITICAL
   Does the brief name at least one credible alternative supplier from
   the alternatives input, with relative cost / capacity / lead-time
   stated? "We have other options" without specifics is NOT a BATNA.
   Flag every unsupported or hand-waved alternative under BATNA FLAGS:.

2. COST-FLOOR INTEGRITY (25%) — CRITICAL
   Is the buyer's target_terms ask defensible against the cost_drivers
   input (commodity moves, freight, FX, supplier margin headroom)? An
   ask below a defensible cost floor will either be rejected or damage
   the supplier. Flag every unsupported price ask under COST FLAGS:.

3. RELATIONSHIP FIT (20%) — CRITICAL
   Given relationship_context (strategic vs preferred vs commodity), is
   the proposed tactic appropriate? Hardball tactics on a strategic
   supplier without explicit acknowledgement of the cost are a flag.
   Surface under RELATIONSHIP FLAGS:.

4. CONSTRAINT COVERAGE (15%)
   Does the brief account for every constraint in negotiation_constraints
   (corporate policy, ESG, compliance, MOQ floors)? Missing constraint
   coverage is a quality issue.

5. ACTIONABILITY (10%)
   Is the brief specific: opening offer, target landing zone, walk-away
   point, concession order, talking points keyed to supplier objections?

Overall score = weighted average.
Score ≥ 7.5 AND zero BATNA / COST / RELATIONSHIP flags: brief is ready
for buyer + finance + legal review. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  BATNA FLAGS: [bullet list, or "None detected"]
  COST FLAGS: [bullet list, or "None detected"]
  RELATIONSHIP FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a supplier negotiation brief for a human category
buyer and finance partner to review. You have no deal-closure incentive
— your job is honest BATNA, honest cost-floor, and honest relationship
assessment.

BASE EVERY ALTERNATIVE-SUPPLIER CLAIM ON THE INPUTS. Do not invent
backup suppliers or import generic "competitive alternatives exist"
language not present in the alternatives field.

BASE EVERY COST-FLOOR CLAIM ON THE INPUTS. Do not import a default cost
trajectory ("commodities are trending down") not present in
cost_drivers.

NEGOTIATION REQUEST:
{request_text}

{wiki_context}

Produce a structured negotiation brief with exactly these sections:

## BATNA Assessment
For each alternative named in the alternatives field: relative cost,
capacity, lead time, audit / qualification status. State plainly if no
credible alternative exists — that is a finding, not a failure.

## Cost-Floor Defence
State the buyer's target ask. Then walk through cost_drivers to defend
the floor: what input-cost moves justify the ask, what supplier-margin
headroom is plausible, what would the supplier point to as their cost
floor. If the ask is below a defensible floor, say so.

## Relationship Implications
Given relationship_context, name the cost of the proposed tactic to the
supplier relationship. For strategic suppliers, explicitly acknowledge
multi-year implications. For commodity suppliers, state any sourcing-
continuity risk.

## Opening Offer + Landing Zone + Walk-Away
Three numbers / term-sets: opening offer, target landing zone, walk-
away point. Each anchored in the BATNA and cost-floor sections above.

## Concession Order
If concessions are required, the order in which to give them and what
to demand in return.

## Talking Points
For each likely supplier objection (cost-driver citation, capacity
constraint, relationship appeal), one prepared response keyed to the
inputs.

## Evidence Gaps
Information missing from the inputs that materially affects BATNA
strength, cost-floor defence, or relationship assessment.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this negotiation brief. Address EVERY issue in the reviewer's
critique, especially any BATNA / COST / RELATIONSHIP flags.

PREVIOUS BRIEF:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any BATNA FLAG: either tighten the alternative-supplier claim
to what the inputs actually support, or state plainly that no credible
alternative exists (and adjust opening / walk-away accordingly).
⚠️  For any COST FLAG: re-anchor the cost-floor defence in
cost_drivers; if the ask cannot be defended, raise the target.
⚠️  For any RELATIONSHIP FLAG: either soften the tactic, or explicitly
acknowledge the relationship cost and justify accepting it.
"""


@dataclass
class SupplierBriefRequest:
    """Structured input for the supplier-brief workflow."""

    supplier_name: str
    """Supplier name (or anonymised label)."""

    category: str
    """Category, e.g. 'dairy', 'packaged-meals', 'corrugated-packaging'."""

    current_terms: str
    """Current price, payment terms, MOQ, lead time."""

    target_terms: str
    """What the buyer wants — the ask."""

    volume_history: str
    """Last 12 months of purchase volume + trend."""

    alternatives: str
    """Backup suppliers named, with relative cost / capacity / audit status."""

    cost_drivers: str
    """Input-cost trends (commodities, freight, FX) the supplier may cite."""

    relationship_context: str
    """Strategic vs preferred vs commodity supplier; multi-year implications."""

    negotiation_constraints: str
    """Corporate policies, ESG, compliance, MOQ floors that constrain tactics."""

    def to_prompt_text(self) -> str:
        return "\n".join([
            f"Supplier name: {self.supplier_name}",
            f"Category: {self.category}",
            f"Current terms: {self.current_terms}",
            f"Target terms: {self.target_terms}",
            f"Volume history: {self.volume_history}",
            f"Alternatives: {self.alternatives}",
            f"Cost drivers: {self.cost_drivers}",
            f"Relationship context: {self.relationship_context}",
            f"Negotiation constraints: {self.negotiation_constraints}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "BATNA FLAGS:",
    "COST FLAGS:",
    "RELATIONSHIP FLAGS:",
)


class SupplierBriefWorkflow(BaseWorkflow):
    """
    Adversarial supplier-brief design: executor drafts negotiation brief →
    reviewer challenges BATNA strength, cost-floor defence, and
    relationship implications → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero BATNA FLAGS
        AND zero COST FLAGS
        AND zero RELATIONSHIP FLAGS
    """

    async def run(  # type: ignore[override]
        self,
        request: SupplierBriefRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial supplier-brief loop."""
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
                criteria=_BRIEF_REVIEW_CRITERIA,
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
                "supplier_name": request.supplier_name,
                "category": request.category,
                "batna_flags": list(dict.fromkeys(accumulated["BATNA FLAGS:"])),
                "cost_flags": list(dict.fromkeys(accumulated["COST FLAGS:"])),
                "relationship_flags": list(dict.fromkeys(accumulated["RELATIONSHIP FLAGS:"])),
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
            "BATNA FLAGS:": (
                "⚠️  BATNA FLAGS (tighten the alternative-supplier claim, or state "
                "plainly that no credible alternative exists):"
            ),
            "COST FLAGS:": (
                "⚠️  COST FLAGS (re-anchor cost-floor defence in cost_drivers, or "
                "raise the target ask):"
            ),
            "RELATIONSHIP FLAGS:": (
                "⚠️  RELATIONSHIP FLAGS (soften tactic, or explicitly acknowledge the "
                "relationship cost):"
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
        request: SupplierBriefRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["BATNA FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  BATNA FLAGS DETECTED ({len(accumulated['BATNA FLAGS:'])}) — "
                "category buyer must qualify at least one alternative supplier "
                "(audit status + quoted cost) before opening negotiation"
            )
        if accumulated["COST FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  COST FLAGS DETECTED ({len(accumulated['COST FLAGS:'])}) — "
                "finance must re-validate the cost-floor defence against the "
                "structured cost-driver feed"
            )
        if accumulated["RELATIONSHIP FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  RELATIONSHIP FLAGS DETECTED "
                f"({len(accumulated['RELATIONSHIP FLAGS:'])}) — category leadership "
                "must explicitly accept the multi-year relationship cost of the "
                "proposed tactic before it is used"
            )
        checklist.extend([
            f"[ ] Category buyer review of BATNA strength for {request.supplier_name}",
            "[ ] Finance sign-off: cost-floor defence anchored in input-cost feed",
            "[ ] Legal review of negotiation_constraints coverage (ESG, compliance, MOQ)",
            "[ ] Procurement leadership sign-off on opening / walk-away / concession order",
            "[ ] No AI-generated language sent to supplier without buyer rewrite",
        ])
        return checklist
