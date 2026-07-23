"""
Workflow — Claims Reserve Estimation (P&C Insurance Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to commercial
P&C claims reserve estimation. Executor drafts a reserve recommendation;
reviewer (recommended: different model family per ARIS §2.1 principle 1)
challenges reserve methodology, comparable-case selection, and venue
posture, and can issue a REVIEWER VETO when the proposed reserve poses
SOX-restatement risk.

This workflow uses the **reviewer-veto** pattern (D-RETAIL-1, reused per
D-PC-4): the reviewer can issue a verbatim VETO directive under
`REVIEWER VETO:` to halt the loop immediately. Reserve under-statement is
the canonical SOX-restatement / NAIC-exam risk (AIG 2005, MBIA 2008),
mirroring ARIS §3.2 cross-model audit on irreversible decisions.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Live claims-system integration — comparable_cases is free-text;
       production requires structured query against an analytics warehouse
       fed from Guidewire ClaimCenter / Origami / AS400 extracts so
       comparables are venue-filtered + line-of-business filtered + recency-
       filtered authoritatively, not by paraphrased prose.
    2. Loss-development triangles — IBNR uplift here is an LLM rationale;
       production uses chain-ladder / Bornhuetter-Ferguson on Schedule P
       loss triangles, with the LLM advising the AY/PY adjustment, not
       computing the base estimate.
    3. Venue jury-verdict tables — venue jury propensity should be sourced
       from a structured table (Jury Verdict Reporter, LexisNexis VerdictSearch),
       not described in caller-supplied prose.
    4. Reinsurer notification — proposed reserves above treaty notification
       thresholds must trigger a structured cession notice, not just a
       checklist line item.
    5. Senior actuary + claims-committee sign-off — reserve adequacy is
       SOX-reportable. AI output is advisory; the reserve write-up that
       enters Schedule P must be human-authored and human-signed.
    6. Append-only audit store — every reserve draft, flag, veto, and the
       reviewer critique must be captured in a tamper-evident store
       defensible against NAIC market-conduct exam.
    7. Dedicated third-model actuarial auditor — this workflow folds the
       reserve audit into the same reviewer that scores draft quality.
       Production should run a separately configured model (different
       family from BOTH executor and reviewer) whose only job is reserve-
       adequacy verification against loss-development data. See ARIS §3.1.
    8. Real-time aggregate exposure feed — class-action / multi-claimant
       signals (`regulatory_exposure`) require a structured feed from the
       claims-aggregation system, not analyst-curated prose.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import (
    extract_flags,
    extract_veto_directive,
    sanitize_for_prompt,
    truncate_flag_display,
)
from ...core.workflow import BaseWorkflow, WorkflowResult

# L-PC-3: per-field cap on Request.to_prompt_text. Bounds any single
# caller-supplied field from starving later fields out of the 6000-char
# concatenated-prompt budget enforced at the workflow boundary.
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated reserve recommendation is not "
    "an authorised reserve booking. A credentialed actuary or claims-"
    "committee member must verify the reserve against loss-development "
    "data, comparable-case selection, and treaty-notification thresholds "
    "before any reserve is booked to Schedule P. AI output must never "
    "trigger an automated reserve change."
)

_VETO_BANNER = (
    "⚠️  REVIEWER VETO — workflow halted before convergence. "
    "See metadata['veto_reason']. Escalate to senior actuary / claims "
    "committee immediately; do not book this reserve."
)

_RESERVE_REVIEW_CRITERIA = """\
Evaluate this reserve recommendation on five dimensions. Score each 0–10.

1. RESERVE ADEQUACY (30%) — CRITICAL
   Is the proposed reserve (indemnity + defence cost + IBNR uplift)
   defensible against comparable cases and the stated injury/damage tier?
   Penalise reserves below the comparable-case median without justification,
   missing defence-cost reserve, missing IBNR uplift methodology, ignored
   sub-limits, or overlooked applicable coverage parts. Flag every gap
   under RESERVE FLAGS:.

2. PRECEDENT QUALITY (25%) — CRITICAL
   Are cited comparable cases venue-appropriate (right state, right court
   level), recent (≤7 years for volatile lines), and selection-unbiased
   (not cherry-picked to favour low reserves)? Penalise comparables drawn
   from neutral venues when this matter sits in a plaintiff-friendly venue,
   or vice versa. Flag every comparable-selection issue under PRECEDENT FLAGS:.

3. LITIGATION POSTURE (20%) — CRITICAL
   Does the reserve reflect the actual venue posture (jury propensity,
   typical settlement-vs-verdict ratio), the defense posture (fault
   percentage, contributory negligence), and any class-action / multi-
   claimant / regulator-interest signals? Penalise reserves that assume
   neutral posture when the inputs show otherwise. Flag every
   posture-vs-reserve mismatch under LITIGATION FLAGS:.

4. METHODOLOGICAL TRANSPARENCY (15%)
   Is the IBNR uplift basis stated (loss-development factor, percentage of
   case reserve, severity-trend assumption)? Is the defence-cost reserve
   methodology stated (percentage of indemnity, hourly-rate × estimated
   hours, capped fee)? Penalise opaque uplifts.

5. ACTIONABILITY (10%)
   Are the immediate next steps (treaty notification, sub-limit check,
   coverage-counsel engagement) specific enough for the claims committee
   to execute?

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Catastrophic-injury signal (paraplegia, traumatic brain injury, wrongful
    death, severe burn) but the proposed indemnity reserve is below
    $500,000 with no stated justification.
  • Class-action / multi-claimant signal in regulatory_exposure but the
    reserve is computed per-occurrence with no aggregate consideration.
  • State Attorney General or state DOI inquiry signal in regulatory_exposure
    but the reserve makes no defence-cost provision for regulatory response.
  • Proposed reserve is BELOW the median of cited comparables AND the
    venue is plaintiff-friendly AND no defence-cost reserve is recorded.
  • Proposed reserve would, if booked, fall below the company's
    reserve-authority floor for the applicable approving authority
    (i.e. the draft routes to the wrong sign-off level).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto directive continuation line with
"Overall", "Key issues", or a markdown header (#) — those markers terminate
the veto block in the parser.

Overall score = weighted average.
Score ≥ 7.5 AND zero RESERVE FLAGS AND zero PRECEDENT FLAGS AND zero
LITIGATION FLAGS AND no VETO: reserve is ready for senior-actuary review.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  RESERVE FLAGS: [bullet list, or "None detected"]
  PRECEDENT FLAGS: [bullet list, or "None detected"]
  LITIGATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are preparing a claims reserve recommendation for a senior actuary
and claims committee to review. You have no stake in the outcome. Your
job is to set the reserve at the figure that is defensible against
comparable cases, venue posture, and SOX-reportable Schedule P inclusion
— not to minimise reserve volatility, not to maximise prudence.

BASE THE RESERVE ON THE INPUT DATA. Do not import assumptions from
general claims practice that are not grounded in the specific loss event,
coverage, comparables, venue, and regulatory exposure below.

CLAIM DATA:
{request_text}

{wiki_context}

Produce a structured reserve recommendation with exactly these sections:

## Loss Event Summary
Restate the loss event in one paragraph: date, mechanism, named insured,
severity tier. Note any competing or conflicting evidence about cause or
extent.

## Coverage Analysis
Map the loss to coverage parts and limits in coverage_summary. Identify
applicable per-occurrence + aggregate limits, deductibles / SIR, and any
sub-limits that may apply. Note any coverage-defense issues.

## Indemnity Reserve
Propose an indemnity reserve $-figure. Trace it to the comparable cases
cited; state the median and range of those comparables; justify any
deviation from the median.

## Defence-Cost Reserve
Propose a defence-cost reserve $-figure. State the methodology
(percentage of indemnity, hourly × hours, capped fee) and the basis for
the choice.

## IBNR Uplift
State the IBNR / loss-development uplift applied to the case reserve.
Cite the basis (loss-development factor, severity-trend assumption,
percentage uplift convention for the line of business).

## Venue & Posture Adjustment
State how the reserve is adjusted for the stated venue (jury-friendly
percentage uplift / downlift) and defence posture (fault percentage,
contributory-negligence reduction). Show the math.

## Regulatory & Aggregate Exposure
Address class-action / multi-claimant / regulator signals from
regulatory_exposure. State whether the per-occurrence reserve is
sufficient or whether an aggregate or regulatory-defence component is
required.

## Treaty & Reinsurance Notification
State whether the proposed reserve crosses any treaty notification
threshold; if yes, name the notice.

## Evidence Gaps
Information missing from the inputs that materially affects reserve
accuracy. Note the gap impact.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this reserve recommendation. Address EVERY issue in the reviewer's
critique, especially any RESERVE FLAGS, PRECEDENT FLAGS, or
LITIGATION FLAGS.

PREVIOUS RECOMMENDATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any RESERVE FLAG: adjust the reserve $-figure or methodology to
match comparable-case median and stated severity tier — do not paper over
the gap.
⚠️  For any PRECEDENT FLAG: re-select comparables that match venue and
recency, or remove the unsupported reserve component.
⚠️  For any LITIGATION FLAG: re-state venue / posture / aggregate
adjustments and show the math.
"""


@dataclass
class ClaimsReserveRequest:
    """Structured input for the P&C claims-reserve workflow."""

    loss_event: str
    """Date, location, mechanism, named insured."""

    injury_or_damage: str
    """Bodily-injury severity tier OR property loss type + initial damage
    estimate."""

    coverage_summary: str
    """Policy form, limits (per-occurrence + aggregate), deductible/SIR,
    sub-limits, scheduled endorsements."""

    comparable_cases: str
    """Analyst-cited prior settlements / verdicts with venue + year +
    settlement amount."""

    venue: str
    """State + county + court (jury-friendliness materially affects reserve)."""

    defense_posture: str
    """Fault/no-fault assessment, contributory negligence, comparative-fault
    percentage."""

    medical_or_repair_estimate: str
    """Treating-provider summary OR adjuster property estimate."""

    regulatory_exposure: str
    """Class-action signals, multi-claimant signals, regulator interest (e.g.
    state AG inquiry, state DOI exam)."""

    current_reserve_proposal: str
    """Analyst's first-pass reserve $ + IBNR uplift basis."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Loss event: {self.loss_event[:cap]}",
            f"Injury / damage: {self.injury_or_damage[:cap]}",
            f"Coverage summary: {self.coverage_summary[:cap]}",
            f"Comparable cases: {self.comparable_cases[:cap]}",
            f"Venue: {self.venue[:cap]}",
            f"Defense posture: {self.defense_posture[:cap]}",
            f"Medical / repair estimate: {self.medical_or_repair_estimate[:cap]}",
            f"Regulatory exposure: {self.regulatory_exposure[:cap]}",
            f"Current reserve proposal: {self.current_reserve_proposal[:cap]}",
        ])


class ClaimsReserveWorkflow(BaseWorkflow):
    """
    Adversarial claims-reserve estimation: executor drafts a reserve
    recommendation → reviewer challenges reserve adequacy, comparable
    selection, and venue posture, with the power to VETO → iterate.

    Convergence gate (D-PC-4, mirroring D-RETAIL-1):
        score ≥ threshold
        AND zero RESERVE FLAGS
        AND zero PRECEDENT FLAGS
        AND zero LITIGATION FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately, recording the verbatim veto
    directive in metadata['veto_reason']. Score and flags from the vetoed
    round are also captured. The output banner directs the actuary /
    claims committee to escalate.
    """

    async def run(  # type: ignore[override]
        self,
        request: ClaimsReserveRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial reserve-estimation loop."""
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_reserve_flags: list[str] = []
        current_precedent_flags: list[str] = []
        current_litigation_flags: list[str] = []
        all_reserve_flags: list[str] = []
        all_precedent_flags: list[str] = []
        all_litigation_flags: list[str] = []
        veto_reason: str | None = None
        max_wiki_chars = config.max_wiki_body_chars

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    request_text=request_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                flag_section = self._format_flag_section(
                    current_reserve_flags,
                    current_precedent_flags,
                    current_litigation_flags,
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
                criteria=_RESERVE_REVIEW_CRITERIA,
            )
            score = review.score
            current_reserve_flags = extract_flags(review.critique, "RESERVE FLAGS:")
            current_precedent_flags = extract_flags(review.critique, "PRECEDENT FLAGS:")
            current_litigation_flags = extract_flags(review.critique, "LITIGATION FLAGS:")
            all_reserve_flags.extend(current_reserve_flags)
            all_precedent_flags.extend(current_precedent_flags)
            all_litigation_flags.extend(current_litigation_flags)

            # Audit-trail writes happen BEFORE the veto check (veto is a halt,
            # not a rollback — what was vetoed and why must be recorded for
            # NAIC market-conduct exam and SOX reserve-adequacy review).
            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            veto_reason = self._extract_veto(review.critique, max_wiki_chars)
            if veto_reason is not None:
                break

            if (
                review.approved
                and not current_reserve_flags
                and not current_precedent_flags
                and not current_litigation_flags
            ):
                converged = True
                break

        actuary_checklist = self._build_actuary_checklist(
            request,
            all_reserve_flags,
            all_precedent_flags,
            all_litigation_flags,
            veto_reason,
        )

        output_with_banners = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "loss_event": sanitize_for_prompt(request.loss_event, max_chars=200),
            "reserve_flags": list(dict.fromkeys(all_reserve_flags)),
            "precedent_flags": list(dict.fromkeys(all_precedent_flags)),
            "litigation_flags": list(dict.fromkeys(all_litigation_flags)),
            "actuary_checklist": actuary_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True

        return WorkflowResult(
            output=output_with_banners,
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata=metadata,
        )

    @staticmethod
    def _extract_veto(critique: str, max_chars: int) -> str | None:
        """Thin delegate to `core._internal.extract_veto_directive`
        (M-PC-1 / M2 / L5 hardening). Test API preserved."""
        return extract_veto_directive(critique, "REVIEWER VETO:", max_chars)

    @staticmethod
    def _format_flag_section(
        reserve_flags: list[str],
        precedent_flags: list[str],
        litigation_flags: list[str],
    ) -> str:
        if not reserve_flags and not precedent_flags and not litigation_flags:
            return ""
        parts: list[str] = []
        if reserve_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(reserve_flags)
            )
            parts.append(
                "⚠️  RESERVE FLAGS (adjust reserve $-figure or methodology):\n"
                f"{flags_text}"
            )
        if precedent_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(precedent_flags)
            )
            parts.append(
                "⚠️  PRECEDENT FLAGS (re-select comparables that match venue and recency):\n"
                f"{flags_text}"
            )
        if litigation_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(litigation_flags)
            )
            parts.append(
                "⚠️  LITIGATION FLAGS (re-state venue / posture / aggregate adjustments):\n"
                f"{flags_text}"
            )
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _compose_output(draft: str, veto_reason: str | None) -> str:
        if veto_reason is None:
            return f"{draft}\n\n---\n\n{_DISCLAIMER}"
        return (
            f"{_VETO_BANNER}\n\nVETO DIRECTIVE: {veto_reason}\n\n"
            f"--- Vetoed draft below ---\n\n{draft}\n\n---\n\n{_DISCLAIMER}"
        )

    @staticmethod
    def _build_actuary_checklist(
        request: ClaimsReserveRequest,
        reserve_flags: list[str],
        precedent_flags: list[str],
        litigation_flags: list[str],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = []
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — escalate to senior actuary / claims "
                "committee BEFORE booking; do not record this reserve to Schedule P"
            )
        if reserve_flags:
            checklist.append(
                f"[ ] ⚠️  RESERVE FLAGS DETECTED ({len(reserve_flags)}) — re-base "
                "indemnity + defence + IBNR against loss-development triangle"
            )
        if precedent_flags:
            checklist.append(
                f"[ ] ⚠️  PRECEDENT FLAGS DETECTED ({len(precedent_flags)}) — "
                "re-pull comparables filtered by venue and recency"
            )
        if litigation_flags:
            checklist.append(
                f"[ ] ⚠️  LITIGATION FLAGS DETECTED ({len(litigation_flags)}) — "
                "re-state venue posture, aggregate exposure, and regulatory-defence basis"
            )
        checklist.extend([
            "[ ] Senior actuary sign-off if reserve > $1M or veto raised",
            "[ ] Claims committee review per company reserve-authority matrix",
            "[ ] Document comparable-case selection rationale (Schedule P-defensible)",
            f"[ ] Confirm venue posture for: {request.venue}",
            "[ ] Verify treaty notification threshold; notify reinsurer if crossed",
            "[ ] Coverage counsel review if any coverage-defense issue surfaced",
            "[ ] Re-evaluate reserve every 90 days or on material development",
            "[ ] Book reserve — AI output must not trigger automatic reserve change",
        ])
        return checklist
