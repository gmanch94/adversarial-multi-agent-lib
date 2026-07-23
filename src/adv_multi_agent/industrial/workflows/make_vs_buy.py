"""
Workflow — Make-vs-Buy Decision (Industrial Manufacturing Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to the
in-house-vs-external-sourcing boundary for an industrial OEM that
designs and manufactures the majority of its own components (the
"85% in-house" thesis exemplified by Crown Equipment Corporation).

Executor drafts a make-vs-buy recommendation; reviewer (recommended:
different model family per ARIS §2.1 principle 1) challenges
cost-only anchoring, missed IP-leak risk, and over-stated internal
capability.

Triple-flag gate (D-IND-1): COST FLAGS, CAPABILITY FLAGS, IP-LEAK FLAGS.
**No reviewer veto** — make-vs-buy is reversible at the next sourcing
review (typically annual); capacity-discipline + IP integrity are the gate.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PLM integration (Teamcenter / Windchill / Aras) — component_specs
       must come from structured BOM/CAD records, not paraphrased prose.
    2. Should-cost engine — internal_cost_basis must trace to a structured
       activity-based-costing model with labor / overhead / material
       breakdowns, not analyst summary.
    3. Supplier-bid normalization — external_bid_summary must come from
       a structured RFQ system with normalised currency, MOQ, and Incoterm,
       not free-text.
    4. IP-risk taxonomy — IP-leak flags should map to a controlled IP
       taxonomy (process know-how, design IP, trade secret) with
       export-control overlay (EAR / ITAR / dual-use), not narrative.
    5. Capacity model — internal-capacity claims must trace to MES/ERP
       work-center capacity, not assumed available.
    6. Long-term contract terms — supplier longevity, capacity reservation,
       and exit-cost clauses belong in a structured contract repository.
    7. Append-only audit store + dedicated third-model auditor — see
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
    "⚠️  ADVISORY ONLY — This AI-generated make-vs-buy recommendation is "
    "not an authorised sourcing decision. A credentialed sourcing-council "
    "member must verify cost basis, capacity claims, and IP-risk posture "
    "before any contract is awarded or in-house investment is approved. "
    "AI output must never trigger an automated sourcing decision."
)

_MAKEBUY_REVIEW_CRITERIA = """\
Evaluate this make-vs-buy recommendation on four dimensions. Score each 0–10.

1. COST DEFENSIBILITY (30%) — CRITICAL
   Is the internal should-cost defensible (labour + overhead + material +
   capex amortisation + capacity-opportunity)? Is the external bid
   normalised (currency, MOQ, Incoterm, freight, duty, tooling
   amortisation)? Penalise unit-price-only comparisons; flag missing
   total-cost-of-ownership elements under COST FLAGS:.

2. CAPABILITY HONESTY (30%) — CRITICAL
   Does the internal-capability claim match the actual process maturity
   (PPAP / PFMEA / Cpk evidence), tooling availability, and engineering
   bandwidth? Is the external-supplier capability claim backed by
   audit / PPAP / first-article? Penalise capability hand-waving and
   "we can do this" claims with no evidence trail. Flag every gap under
   CAPABILITY FLAGS:.

3. IP-LEAK / STRATEGIC RISK (25%) — CRITICAL
   Does the recommendation expose core process know-how or design IP to a
   geography or supplier with elevated leak / counterfeit / forced-tech-
   transfer risk? Are export-control classifications (EAR / ITAR / EU
   dual-use) addressed? Penalise outsourcing of differentiating processes
   without an IP-protection plan. Flag every issue under IP-LEAK FLAGS:.

4. ACTIONABILITY (15%)
   Are the next steps (contract term, capacity reservation, exit clause,
   parallel-tooling plan, supplier-development plan) specific enough for
   the sourcing council to act on?

Overall score = weighted average.
Score ≥ 7.5 AND zero COST FLAGS AND zero CAPABILITY FLAGS AND zero
IP-LEAK FLAGS: recommendation is ready for sourcing-council review.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  COST FLAGS: [bullet list, or "None detected"]
  CAPABILITY FLAGS: [bullet list, or "None detected"]
  IP-LEAK FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a make-vs-buy recommendation for an industrial OEM's
sourcing council. You have no stake in the outcome. Your job is to
recommend the option (make in-house, buy external, dual-source, or
parallel-tool) that is defensible on total cost, capability evidence, and
IP-risk posture — not to chase unit-price savings, not to assume
internal capability without evidence.

BASE THE RECOMMENDATION ON THE INPUT DATA.

SOURCING DATA:
{request_text}

{wiki_context}

Produce a structured recommendation with exactly these sections:

## Component Summary
Restate the component, annual demand, design ownership, and any inter-
dependencies (sub-assemblies, common platforms).

## Internal Should-Cost
Build up internal cost: material + labour + overhead + capex amortisation
+ capacity-opportunity cost. State the basis for each line item.

## External Bid Normalisation
Normalise external supplier bids: currency, MOQ, Incoterm, freight, duty,
tooling amortisation. State the year-1 vs steady-state delta.

## Capability Position
For the in-house option: state the process maturity evidence (PPAP, Cpk,
PFMEA) and the tooling / capacity readiness. For the external option:
state the supplier's audit history, first-article status, and capacity
runway.

## IP and Strategic Risk
Identify the IP class at risk (process know-how, design IP, trade secret)
and the geography / supplier risk overlay (export-control, forced-tech-
transfer regimes, counterfeit history). Propose an IP-protection plan if
external sourcing is recommended.

## Recommendation
Make in-house / Buy external / Dual-source / Parallel-tool. State the
contract term, capacity reservation, and exit-cost clauses required.

## Evidence Gaps
Information missing from the inputs that materially affects the
recommendation.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this make-vs-buy recommendation. Address EVERY issue in the
reviewer's critique, especially any COST FLAGS, CAPABILITY FLAGS, or
IP-LEAK FLAGS.

PREVIOUS RECOMMENDATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any COST FLAG: re-state the should-cost build-up or normalise the
external bid against the missing dimension — do not paper over the gap.
⚠️  For any CAPABILITY FLAG: cite the process-maturity evidence or
downgrade the capability claim.
⚠️  For any IP-LEAK FLAG: state the IP class at risk and the protection
plan, or revise the recommendation away from the exposed option.
"""


@dataclass
class MakeVsBuyRequest:
    """Structured input for the industrial make-vs-buy workflow."""

    component_summary: str
    """Component name, annual demand, design ownership, sub-assembly map."""

    internal_cost_basis: str
    """Should-cost build-up: material + labour + overhead + capex + capacity
    opportunity cost."""

    external_bid_summary: str
    """Normalised supplier bids: unit price, MOQ, Incoterm, freight, duty,
    tooling amortisation."""

    capability_evidence: str
    """Process-maturity evidence for in-house (PPAP, Cpk, PFMEA) AND for
    external (audit history, first-article status)."""

    ip_risk_context: str
    """IP class at risk + geographic / supplier overlay (export-control,
    counterfeit history, forced-tech-transfer regime)."""

    strategic_constraints: str
    """Capacity reservation needs, exit-cost tolerance, platform-commonality
    requirements, long-term contract horizon."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Component summary: {self.component_summary[:cap]}",
            f"Internal cost basis: {self.internal_cost_basis[:cap]}",
            f"External bid summary: {self.external_bid_summary[:cap]}",
            f"Capability evidence: {self.capability_evidence[:cap]}",
            f"IP risk context: {self.ip_risk_context[:cap]}",
            f"Strategic constraints: {self.strategic_constraints[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "COST FLAGS:",
    "CAPABILITY FLAGS:",
    "IP-LEAK FLAGS:",
)


class MakeVsBuyWorkflow(BaseWorkflow):
    """
    Adversarial make-vs-buy review: executor drafts a sourcing recommendation
    → reviewer challenges cost build-up, capability evidence, and IP-risk
    posture → iterate.

    Convergence gate (D-IND-1):
        score ≥ threshold
        AND zero COST FLAGS
        AND zero CAPABILITY FLAGS
        AND zero IP-LEAK FLAGS

    No reviewer veto — sourcing decisions are reversible at the next
    sourcing-review cycle.
    """

    async def run(  # type: ignore[override]
        self,
        request: MakeVsBuyRequest,
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
                criteria=_MAKEBUY_REVIEW_CRITERIA,
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

        approver_checklist = self._build_approver_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "component_summary": sanitize_for_prompt(
                    request.component_summary, max_chars=200
                ),
                "cost_flags": list(dict.fromkeys(accumulated["COST FLAGS:"])),
                "capability_flags": list(dict.fromkeys(accumulated["CAPABILITY FLAGS:"])),
                "ip_leak_flags": list(dict.fromkeys(accumulated["IP-LEAK FLAGS:"])),
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
            "COST FLAGS:": (
                "⚠️  COST FLAGS (re-state should-cost build-up or normalise "
                "the external bid against the missing dimension):"
            ),
            "CAPABILITY FLAGS:": (
                "⚠️  CAPABILITY FLAGS (cite process-maturity evidence or "
                "downgrade the capability claim):"
            ),
            "IP-LEAK FLAGS:": (
                "⚠️  IP-LEAK FLAGS (state IP class at risk + protection plan, "
                "or revise away from the exposed option):"
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
        request: MakeVsBuyRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["COST FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  COST FLAGS ({len(accumulated['COST FLAGS:'])}) — "
                "re-base should-cost against ABC model + normalise external bid TCO"
            )
        if accumulated["CAPABILITY FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  CAPABILITY FLAGS ({len(accumulated['CAPABILITY FLAGS:'])}) — "
                "produce PPAP / Cpk / first-article evidence before commit"
            )
        if accumulated["IP-LEAK FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  IP-LEAK FLAGS ({len(accumulated['IP-LEAK FLAGS:'])}) — "
                "document IP class + protection plan; legal/export-control review"
            )
        checklist.extend([
            "[ ] Sourcing council sign-off per authority matrix",
            "[ ] Finance: should-cost reconciliation against ERP standard cost",
            "[ ] Engineering: PFMEA delta for the recommended sourcing option",
            "[ ] Legal / IP counsel review if external sourcing of differentiating process",
            f"[ ] Confirm strategic constraint coverage: {request.strategic_constraints[:60]}",
            "[ ] Award contract / approve capex — AI output must not trigger automatic action",
        ])
        return checklist
