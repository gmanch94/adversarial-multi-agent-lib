"""
Workflow — Supplier Qualification (Industrial Manufacturing Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to onboarding
or re-qualifying an external supplier for the externally-sourced portion
of an OEM's BOM (the "15%" complement to in-house manufacturing).

Executor drafts a supplier-qualification recommendation; reviewer
(recommended: different model family per ARIS §2.1 principle 1)
challenges financial-stress signals an executor's "all checks pass"
summary would gloss, quality-system evidence, and geographic concentration.

Triple-flag gate (D-IND-1): FINANCIAL FLAGS, QUALITY FLAGS,
GEO-CONCENTRATION FLAGS. **No reviewer veto** — supplier disqualification
is reversible; the gate is evidence-discipline, not life-safety halt.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. D&B / RapidRatings / Resilinc integration — financial-stress signals
       must come from a structured supplier-risk feed, not analyst summary.
    2. Quality-system evidence — IATF 16949 / ISO 9001 audit reports, PPAP
       status, and SCAR history must come from a structured QMS, not prose.
    3. Geographic-concentration model — sub-tier mapping (Tier-2 / Tier-3)
       must come from a structured supply-chain visibility platform
       (Resilinc, Interos), not caller-supplied claims.
    4. Sanctions / export-control screening — entity-list and dual-use
       checks (OFAC SDN, BIS Entity List, EU consolidated, UN) must be
       structured screening, not narrative.
    5. Continuity / business-resilience evidence — BCP/DRP and insurance
       certificates must be verified against carrier records.
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
    "⚠️  ADVISORY ONLY — This AI-generated supplier-qualification "
    "recommendation is not an authorised onboarding decision. A "
    "credentialed supplier-development engineer and procurement-council "
    "member must verify financial, quality, and concentration evidence "
    "before any qualification is granted. AI output must never trigger "
    "an automated supplier approval."
)

_SUPPLIER_REVIEW_CRITERIA = """\
Evaluate this supplier-qualification recommendation on four dimensions.
Score each 0–10.

1. FINANCIAL STRENGTH (30%) — CRITICAL
   Is the supplier's financial position evidenced by recent audited
   statements, D&B / RapidRatings / Z-score signals, and concentration of
   customer base? Penalise "we have not heard of any issues" framing
   that hides genuine stress (negative working capital, covenant
   pressure, late payments to sub-tier). Flag every gap under
   FINANCIAL FLAGS:.

2. QUALITY SYSTEM (30%) — CRITICAL
   Does the supplier hold the required certifications (IATF 16949 / ISO
   9001 / AS9100 as applicable) with current audit evidence? Is PPAP
   status appropriate for the planned parts? SCAR / 8D history available?
   Penalise self-attested quality claims with no audit evidence. Flag
   every gap under QUALITY FLAGS:.

3. GEOGRAPHIC / CONCENTRATION (25%) — CRITICAL
   Does this qualification create a single-geography or single-supplier
   dependency for the affected commodity? Are Tier-2 / Tier-3 sub-suppliers
   mapped and resilient? Are sanctions / export-control screens current?
   Flag every issue under GEO-CONCENTRATION FLAGS:.

4. ACTIONABILITY (15%)
   Are the next steps (PPAP plan, capacity reservation, BCP/DRP review,
   sub-tier audit, contract terms, supplier-development plan) specific
   enough for the procurement council to act on?

Overall score = weighted average.
Score ≥ 7.5 AND zero FINANCIAL FLAGS AND zero QUALITY FLAGS AND zero
GEO-CONCENTRATION FLAGS: recommendation is ready for procurement-council
review. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  FINANCIAL FLAGS: [bullet list, or "None detected"]
  QUALITY FLAGS: [bullet list, or "None detected"]
  GEO-CONCENTRATION FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a supplier-qualification recommendation for an
industrial OEM's procurement council. You have no stake in the outcome.
Your job is to recommend Qualified / Conditionally Qualified / Not
Qualified with evidence — not to push approvals through, not to
over-reject on conservative defaults.

BASE THE RECOMMENDATION ON THE INPUT DATA.

SUPPLIER DATA:
{request_text}

{wiki_context}

Produce a structured recommendation with exactly these sections:

## Supplier Summary
Restate the supplier name, location(s), commodity covered, annual spend
proposed, and incumbency status (new / re-qualify / disqualify review).

## Financial Position
Summarise audited-statement signals, third-party ratings (D&B / RapidRatings
/ Altman Z), customer concentration, and any working-capital stress signal.

## Quality System
Certifications held + current audit dates; PPAP status for planned parts;
SCAR / 8D history; any prior escapes.

## Capacity and Continuity
Capacity reservation availability; BCP/DRP maturity; insurance and bond
evidence; backup-tooling posture.

## Sub-Tier and Geographic Posture
Tier-2 / Tier-3 mapping where known; sanctions / export-control screening
status; geographic concentration vs OEM's other sources for this commodity.

## Recommendation
Qualified / Conditionally Qualified (with conditions) / Not Qualified.
State the conditions, monitoring cadence, and re-qualification trigger.

## Evidence Gaps
Information missing from the inputs that materially affects the
recommendation.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this supplier-qualification recommendation. Address EVERY issue in
the reviewer's critique, especially any FINANCIAL FLAGS, QUALITY FLAGS,
or GEO-CONCENTRATION FLAGS.

PREVIOUS RECOMMENDATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any FINANCIAL FLAG: cite the financial evidence with year and
source, or downgrade the recommendation to Conditionally Qualified with
financial-monitoring condition.
⚠️  For any QUALITY FLAG: cite the audit / PPAP / SCAR evidence or add a
quality-system development condition.
⚠️  For any GEO-CONCENTRATION FLAG: state the dual-source / sub-tier
resilience plan or revise the recommendation.
"""


@dataclass
class SupplierQualificationRequest:
    """Structured input for the industrial supplier-qualification workflow."""

    supplier_summary: str
    """Name, location(s), commodity, planned annual spend, incumbency status."""

    financial_signals: str
    """Audited-statement summary + third-party ratings + customer-concentration
    + any working-capital stress signals."""

    quality_evidence: str
    """Certifications + audit dates + PPAP status + SCAR / 8D history."""

    capacity_and_continuity: str
    """Capacity reservation, BCP/DRP status, insurance/bond evidence,
    backup-tooling posture."""

    sub_tier_and_geographic: str
    """Tier-2 / Tier-3 mapping + sanctions / export-control screening +
    geographic-concentration overlay."""

    proposed_qualification: str
    """The procurement engineer's first-pass recommendation
    (Qualified / Conditional / Not Qualified) and any stated conditions."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Supplier summary: {self.supplier_summary[:cap]}",
            f"Financial signals: {self.financial_signals[:cap]}",
            f"Quality evidence: {self.quality_evidence[:cap]}",
            f"Capacity and continuity: {self.capacity_and_continuity[:cap]}",
            f"Sub-tier and geographic: {self.sub_tier_and_geographic[:cap]}",
            f"Proposed qualification: {self.proposed_qualification[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "FINANCIAL FLAGS:",
    "QUALITY FLAGS:",
    "GEO-CONCENTRATION FLAGS:",
)


class SupplierQualificationWorkflow(BaseWorkflow):
    """
    Adversarial supplier-qualification review: executor drafts a Qualified /
    Conditional / Not Qualified recommendation → reviewer challenges
    financial stress, quality-system evidence, and geographic concentration
    → iterate.

    Convergence gate (D-IND-1):
        score ≥ threshold
        AND zero FINANCIAL FLAGS
        AND zero QUALITY FLAGS
        AND zero GEO-CONCENTRATION FLAGS

    No reviewer veto — supplier qualification is reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: SupplierQualificationRequest,
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
                criteria=_SUPPLIER_REVIEW_CRITERIA,
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
                "supplier_summary": request.supplier_summary,
                "financial_flags": list(dict.fromkeys(accumulated["FINANCIAL FLAGS:"])),
                "quality_flags": list(dict.fromkeys(accumulated["QUALITY FLAGS:"])),
                "geo_concentration_flags": list(
                    dict.fromkeys(accumulated["GEO-CONCENTRATION FLAGS:"])
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
            "FINANCIAL FLAGS:": (
                "⚠️  FINANCIAL FLAGS (cite financial evidence or add financial-"
                "monitoring condition):"
            ),
            "QUALITY FLAGS:": (
                "⚠️  QUALITY FLAGS (cite audit / PPAP / SCAR evidence or add "
                "quality-development condition):"
            ),
            "GEO-CONCENTRATION FLAGS:": (
                "⚠️  GEO-CONCENTRATION FLAGS (state dual-source / sub-tier "
                "resilience plan or revise recommendation):"
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
        request: SupplierQualificationRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["FINANCIAL FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  FINANCIAL FLAGS ({len(accumulated['FINANCIAL FLAGS:'])}) — "
                "obtain audited statements + third-party rating; finance review"
            )
        if accumulated["QUALITY FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  QUALITY FLAGS ({len(accumulated['QUALITY FLAGS:'])}) — "
                "schedule on-site audit; verify PPAP / 8D history"
            )
        if accumulated["GEO-CONCENTRATION FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  GEO-CONCENTRATION FLAGS "
                f"({len(accumulated['GEO-CONCENTRATION FLAGS:'])}) — "
                "map Tier-2 / Tier-3; refresh sanctions / export-control screen"
            )
        checklist.extend([
            "[ ] Procurement council sign-off per authority matrix",
            "[ ] Supplier-development engineer on-site audit before first PPAP",
            "[ ] Legal review of supplier-agreement + IP / data-handling clauses",
            f"[ ] Confirm capacity reservation: {request.capacity_and_continuity[:60]}",
            "[ ] Sanctions / export-control screen refresh prior to award",
            "[ ] Award qualification — AI output must not trigger automatic approval",
        ])
        return checklist
