"""
Workflow — Complex Commercial Underwriting (P&C Insurance Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to complex
commercial-lines underwriting (hazardous-class manufacturer, contractor,
specialty risk). Executor drafts bind terms; reviewer (recommended:
different model family per ARIS §2.1 principle 1) challenges loss-cost
basis, exclusion completeness, and capacity allocation.

Triple-flag gate (D-PC-4): LOSS-COST FLAGS, EXCLUSION FLAGS,
CAPACITY FLAGS. **No reviewer veto** — bind decisions are reversible at
the next renewal in most cases, so capacity-discipline is the gate, not
life-safety halt.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. ISO loss-cost tables — proposed premium adequacy should be checked
       against the filed ISO loss-cost × LCM, not paraphrased from prose.
    2. Class-code / hazard-grade authoritative lookup — class codes
       (NCCI / ISO) and hazard tiers should resolve against a structured
       table, not be caller-supplied.
    3. Loss-run normalization — prior_loss_history is free-text; production
       requires triangle-normalized run with developed losses.
    4. Real-time aggregate exposure — capacity_constraint must reflect the
       live portfolio aggregate cap and treaty cession state.
    5. State filing / rate-adequacy engine — admitted vs surplus-lines
       routing, filed-deviation availability, and rate-adequacy filings
       should be structured rules, not prose.
    6. Underwriter authority matrix — proposed terms must route to the
       correct authority level; production needs the company authority
       matrix wired in.
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

# L-PC-3: per-field cap (see claims_reserve.py for rationale).
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated underwriting recommendation is "
    "not an authorised quote or bind. A credentialed underwriter must "
    "verify loss-cost basis, exclusion completeness, and capacity / "
    "reinsurance pre-clearance before any bind is communicated. AI output "
    "must never trigger an automated bind."
)

_UW_REVIEW_CRITERIA = """\
Evaluate this underwriting recommendation on four dimensions. Score each 0–10.

1. LOSS-COST DEFENSIBILITY (35%) — CRITICAL
   Is the proposed premium defensible against the ISO loss-cost × company
   LCM (loss-cost multiplier) for this class code and territory? Is the
   expense-ratio assumption inside the filed band? If the filing supports
   deviation, is the deviation justified? Flag every loss-cost gap under
   LOSS-COST FLAGS:.

2. EXCLUSION COMPLETENESS (30%) — CRITICAL
   For the stated hazard grade and operations, are the standard
   class-specific exclusions present (mold/silica for construction;
   lead/asbestos for older premises; cyber / data for technology services;
   abuse/molestation for human-services classes; absolute pollution for
   contractors handling hazmat)? Do scheduled endorsements contradict the
   main form? Flag every exclusion gap under EXCLUSION FLAGS:.

3. CAPACITY DISCIPLINE (25%) — CRITICAL
   Would this bind exceed the line-of-business aggregate cap? Is treaty
   cession pre-cleared for the requested limits? Does the cat-zone
   concentration (named-storm, earthquake, wildfire) breach the territorial
   cap? Flag every capacity issue under CAPACITY FLAGS:.

4. ACTIONABILITY (10%)
   Are the bind terms (premium, retention, exclusions, sub-limits, scheduled
   endorsements) specific enough for the bind clerk to execute? Is the
   approving authority named?

Overall score = weighted average.
Score ≥ 7.5 AND zero LOSS-COST FLAGS AND zero EXCLUSION FLAGS AND zero
CAPACITY FLAGS: recommendation is ready for senior-underwriter review.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  LOSS-COST FLAGS: [bullet list, or "None detected"]
  EXCLUSION FLAGS: [bullet list, or "None detected"]
  CAPACITY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a commercial underwriting recommendation for a senior
underwriter to review. You have no stake in the outcome. Your job is to
set bind terms that are defensible against ISO loss-cost, complete on
class-specific exclusions, and within capacity discipline — not to chase
premium volume, not to over-restrict.

BASE THE TERMS ON THE INPUT DATA.

SUBMISSION DATA:
{request_text}

{wiki_context}

Produce a structured underwriting recommendation with exactly these sections:

## Insured Summary
Restate the insured's operations, NAICS class, and exposure base.

## Hazard Grade
State the hazard grade, special hazards, and any class-specific risk drivers.

## Loss-History Analysis
Frequency + severity of prior losses; trend direction; any large-loss tail.

## Proposed Premium and Terms
Premium, retention / SIR, deductibles, limits, sub-limits, scheduled
endorsements. Trace the premium back to ISO loss-cost × LCM with stated
deviation (if any).

## Exclusion Schedule
List standard and class-specific exclusions to be attached. Cite the form
number / endorsement number for each.

## Capacity Check
State the LOB aggregate available, treaty cession status, cat-zone
concentration for this risk.

## Coverage Coordination
Note any umbrella attachment, primary/excess sequencing, or reinsurer-
specific approvals required.

## Evidence Gaps
Information missing from the inputs that materially affects the terms.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this underwriting recommendation. Address EVERY issue in the
reviewer's critique, especially any LOSS-COST FLAGS, EXCLUSION FLAGS,
or CAPACITY FLAGS.

PREVIOUS RECOMMENDATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any LOSS-COST FLAG: re-anchor the premium to ISO loss-cost × LCM
or state the filed deviation that supports the proposed figure.
⚠️  For any EXCLUSION FLAG: add the missing class-specific exclusion or
state the explicit reason it does not apply.
⚠️  For any CAPACITY FLAG: reduce the requested limit, pre-clear additional
treaty cession, or refer to senior underwriter for capacity decision.
"""


@dataclass
class CommercialUnderwritingRequest:
    """Structured input for the P&C commercial-underwriting workflow."""

    insured_summary: str
    """NAICS code, exposure base (payroll/receipts/sq.ft.), operations summary."""

    prior_loss_history: str
    """5-year loss runs with frequency + severity."""

    hazard_grade: str
    """Class-code-derived hazard tier + special hazards (hot work, fleet age,
    hazardous materials)."""

    requested_coverage: str
    """Lines, limits, deductibles, scheduled endorsements being requested."""

    proposed_terms: str
    """Premium, retention, exclusions added, sub-limits being proposed."""

    regulatory_context: str
    """State filings required, admitted vs surplus-lines, rate-adequacy
    filing status."""

    capacity_constraint: str
    """Line-of-business aggregate cap, treaty cession status, catastrophe-zone
    exposure."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Insured summary: {self.insured_summary[:cap]}",
            f"Prior loss history: {self.prior_loss_history[:cap]}",
            f"Hazard grade: {self.hazard_grade[:cap]}",
            f"Requested coverage: {self.requested_coverage[:cap]}",
            f"Proposed terms: {self.proposed_terms[:cap]}",
            f"Regulatory context: {self.regulatory_context[:cap]}",
            f"Capacity constraint: {self.capacity_constraint[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "LOSS-COST FLAGS:",
    "EXCLUSION FLAGS:",
    "CAPACITY FLAGS:",
)


class CommercialUnderwritingWorkflow(BaseWorkflow):
    """
    Adversarial commercial-underwriting review: executor drafts bind terms
    → reviewer challenges loss-cost basis, exclusion completeness, and
    capacity discipline → iterate.

    Convergence gate (D-PC-4):
        score ≥ threshold
        AND zero LOSS-COST FLAGS
        AND zero EXCLUSION FLAGS
        AND zero CAPACITY FLAGS

    No reviewer veto: bind decisions are reversible at renewal in most
    commercial lines; capacity discipline is the gate.
    """

    async def run(  # type: ignore[override]
        self,
        request: CommercialUnderwritingRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial commercial-underwriting loop."""
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
                criteria=_UW_REVIEW_CRITERIA,
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
                "insured_summary": sanitize_for_prompt(
                    request.insured_summary, max_chars=200
                ),
                "loss_cost_flags": list(dict.fromkeys(accumulated["LOSS-COST FLAGS:"])),
                "exclusion_flags": list(dict.fromkeys(accumulated["EXCLUSION FLAGS:"])),
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
            "LOSS-COST FLAGS:": (
                "⚠️  LOSS-COST FLAGS (re-anchor premium to ISO loss-cost × LCM or "
                "cite the filed deviation):"
            ),
            "EXCLUSION FLAGS:": (
                "⚠️  EXCLUSION FLAGS (add the missing class-specific exclusion or "
                "state why it does not apply):"
            ),
            "CAPACITY FLAGS:": (
                "⚠️  CAPACITY FLAGS (reduce limit, pre-clear treaty cession, or "
                "refer to senior underwriter):"
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
        request: CommercialUnderwritingRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["LOSS-COST FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  LOSS-COST FLAGS ({len(accumulated['LOSS-COST FLAGS:'])}) — "
                "re-anchor premium against the filed ISO loss-cost × LCM"
            )
        if accumulated["EXCLUSION FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  EXCLUSION FLAGS ({len(accumulated['EXCLUSION FLAGS:'])}) — "
                "schedule missing class-specific exclusions before bind"
            )
        if accumulated["CAPACITY FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  CAPACITY FLAGS ({len(accumulated['CAPACITY FLAGS:'])}) — "
                "confirm LOB aggregate availability and treaty cession pre-clearance"
            )
        checklist.extend([
            "[ ] Senior underwriter review per company authority matrix",
            f"[ ] Confirm hazard grade against class-code authoritative table: {request.hazard_grade[:60]}",
            "[ ] Confirm filed rate-adequacy basis (admitted) or surplus-lines stamp",
            "[ ] Pre-clear reinsurance cession if limits exceed treaty retention",
            "[ ] Issue bind — AI output must not trigger automatic quote / bind",
        ])
        return checklist
