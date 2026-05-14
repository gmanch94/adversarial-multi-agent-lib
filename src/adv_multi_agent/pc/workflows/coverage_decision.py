"""
Workflow — Coverage / Bad-Faith Decision (P&C Insurance Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to commercial
P&C coverage interpretation and bad-faith risk screening. Executor drafts
a coverage decision (cover / partial / deny); reviewer (recommended:
different model family per ARIS §2.1 principle 1) challenges policy
wording, case-law citations, and bad-faith exposure, and can issue a
REVIEWER VETO when the proposed decision creates bad-faith / class-rep
exposure.

This workflow uses the **reviewer-veto** pattern (D-RETAIL-1, reused per
D-PC-4): bad-faith claim handling is litigation-magnifying and creates
punitive-damages exposure that score-alone cannot capture.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Authoritative policy-wording feed — policy_wording is free-text;
       production requires retrieval against the actual policy form library
       (ISO form catalog + company endorsements) so wording is verbatim and
       version-correct.
    2. Case-law retrieval — case-law citations should resolve against a
       structured legal database (Westlaw / Lexis Shepard's), not be
       paraphrased from analyst memory.
    3. State-law choice-of-law engine — governing law and applicable
       doctrines (reasonable expectations, contra proferentem) vary by
       state; production needs a structured rule-base, not caller-supplied
       prose.
    4. Coverage counsel review — denial decisions on contested coverage
       must be reviewed by external coverage counsel. AI output is
       advisory.
    5. Append-only audit store — every coverage draft + critique + veto
       must be captured tamper-evident for bad-faith defence.
    6. Dedicated third-model bad-faith auditor — see ARIS §3.1.
    7. Insured-notice + reservation-of-rights generation — denial /
       partial-coverage decisions trigger notice obligations; production
       must auto-draft and route those notices, not just flag them.
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

# L-PC-3: per-field cap (see claims_reserve.py for rationale).
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated coverage analysis is not an "
    "authorised coverage decision. Coverage counsel must verify policy "
    "wording, case-law authority, and bad-faith exposure before any "
    "decision is communicated to the insured. AI output must never "
    "trigger an automated denial."
)

_VETO_BANNER = (
    "⚠️  REVIEWER VETO — workflow halted before convergence. "
    "See metadata['veto_reason']. Escalate to coverage counsel immediately; "
    "do not communicate this decision to the insured."
)

_COVERAGE_REVIEW_CRITERIA = """\
Evaluate this coverage decision on four dimensions. Score each 0–10.

1. WORDING FIDELITY (35%) — CRITICAL
   Does the cited exclusion / insuring-agreement clause actually map to the
   loss mechanism described in claim_summary? Is the citation verbatim from
   policy_wording, not paraphrased? Is any ambiguity flagged for
   contra proferentem resolution? Does the analysis address reasonable
   expectations doctrine where applicable? Flag every wording gap under
   WORDING FLAGS:.

2. CASE-LAW AUTHORITY (30%) — CRITICAL
   Are cited precedents in the correct jurisdiction (governing state, right
   court level)? Are they still good law (not overruled, distinguished, or
   abrogated)? Does the analysis address recent state-supreme-court
   decisions that could change the outcome? Flag every authority gap under
   CASE-LAW FLAGS:.

3. BAD-FAITH EXPOSURE (25%)
   Does the proposed decision create bad-faith exposure: pattern of delay,
   lowball, claim-handling failure, denial without investigation,
   denial-after-coverage-promise reliance? Material delay creates exposure
   independent of the underlying coverage decision.

4. ACTIONABILITY (10%)
   Are the next steps (reservation-of-rights letter, denial-with-reasons,
   coverage-counsel referral) specific enough for the claims handler to
   execute within the state-mandated response window?

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Proposed decision is a denial AND a reasonable interpretation of the
    policy wording supports coverage (ambiguity in favour of insured).
  • Bad-faith pattern present in the file (delay, lowball history,
    prior insurer communication) AND proposed decision is a denial.
  • Class-action / class-rep signal AND proposed decision creates
    pattern-of-conduct exposure across the class.
  • Cited case-law authority has been overruled or is plainly distinguishable
    on facts; analysis builds on it without addressing the distinguishing
    factor.
  • Reasonable-expectations doctrine clearly applies AND analysis ignores
    it.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto directive continuation line with
"Overall", "Key issues", or a markdown header (#) — those markers terminate
the veto block in the parser.

Overall score = weighted average.
Score ≥ 7.5 AND zero WORDING FLAGS AND zero CASE-LAW FLAGS AND no VETO:
decision is ready for coverage-counsel review.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  WORDING FLAGS: [bullet list, or "None detected"]
  CASE-LAW FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are preparing a coverage decision draft for coverage counsel to
review. You have no stake in the outcome. Your job is to apply the policy
wording to the claim facts and to surface any bad-faith or
class-rep exposure — not to maximise denial, not to maximise coverage.

BASE THE DECISION ON THE INPUT DATA. Do not import general insurance
practice that is not grounded in the specific policy_wording, factual
disputes, governing state_law, and bad_faith_exposure context below.

CLAIM AND POLICY DATA:
{request_text}

{wiki_context}

Produce a structured coverage analysis with exactly these sections:

## Claim Summary
Restate the insured's claim in one paragraph: what is claimed, when,
against which coverage part.

## Applicable Wording
Quote (verbatim from policy_wording) the insuring agreement, exclusions,
conditions, and endorsements relevant to this claim. State which clause
controls.

## Factual-Dispute Analysis
For each contested fact (from factual_disputes), state whose burden it is
and how it affects coverage.

## Coverage Conclusion
State the proposed decision: full coverage / partial / denial. Trace it
back to the controlling clause and the factual-dispute analysis.

## Case-Law Authority
Cite controlling precedents in the governing state (from state_law). For
each, state the holding and how it applies. Address contra proferentem and
reasonable-expectations doctrine if applicable.

## Bad-Faith Screen
Address the bad-faith risk factors from bad_faith_exposure. Note any
delay history, prior lowball, surplus-lines flag, claim-handling pattern.

## Next Actions
Reservation-of-rights letter? Denial-with-reasons letter? Coverage-counsel
referral? State the state-mandated response window.

## Evidence Gaps
Information missing from the inputs that materially affects the analysis.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this coverage analysis. Address EVERY issue in the reviewer's
critique, especially any WORDING FLAGS or CASE-LAW FLAGS.

PREVIOUS ANALYSIS:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any WORDING FLAG: quote the policy wording verbatim and re-map
the loss mechanism to the controlling clause — do not paraphrase the
gap away.
⚠️  For any CASE-LAW FLAG: replace the cited authority with one that is
in-jurisdiction, current, and on-point — or remove the unsupported
conclusion.
"""


@dataclass
class CoverageDecisionRequest:
    """Structured input for the P&C coverage / bad-faith workflow."""

    claim_summary: str
    """What the insured is claiming, when, against which coverage part."""

    policy_wording: str
    """Verbatim relevant clauses (insuring agreement, exclusions, conditions,
    endorsements)."""

    factual_disputes: str
    """What facts are contested between insurer and insured."""

    state_law: str
    """Governing law (state choice-of-law if multi-state); relevant doctrines."""

    bad_faith_exposure: str
    """Prior insurer communications, delay history, surplus-lines flag,
    claim-handling pattern."""

    proposed_decision: str
    """Cover / partial / denial + rationale being proposed for review."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Claim summary: {self.claim_summary[:cap]}",
            f"Policy wording: {self.policy_wording[:cap]}",
            f"Factual disputes: {self.factual_disputes[:cap]}",
            f"State law: {self.state_law[:cap]}",
            f"Bad-faith exposure: {self.bad_faith_exposure[:cap]}",
            f"Proposed decision: {self.proposed_decision[:cap]}",
        ])


class CoverageDecisionWorkflow(BaseWorkflow):
    """
    Adversarial coverage / bad-faith decision review: executor drafts
    decision → reviewer challenges wording fidelity, case-law authority,
    and bad-faith exposure, with the power to VETO → iterate.

    Convergence gate (D-PC-4, mirroring D-RETAIL-1):
        score ≥ threshold
        AND zero WORDING FLAGS
        AND zero CASE-LAW FLAGS
        AND no REVIEWER VETO
    """

    async def run(  # type: ignore[override]
        self,
        request: CoverageDecisionRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial coverage-decision loop."""
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_wording_flags: list[str] = []
        current_case_law_flags: list[str] = []
        all_wording_flags: list[str] = []
        all_case_law_flags: list[str] = []
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
                    current_wording_flags, current_case_law_flags
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
                criteria=_COVERAGE_REVIEW_CRITERIA,
            )
            score = review.score
            current_wording_flags = extract_flags(review.critique, "WORDING FLAGS:")
            current_case_law_flags = extract_flags(review.critique, "CASE-LAW FLAGS:")
            all_wording_flags.extend(current_wording_flags)
            all_case_law_flags.extend(current_case_law_flags)

            # Audit-trail writes happen BEFORE the veto check.
            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            veto_reason = self._extract_veto(review.critique, max_wiki_chars)
            if veto_reason is not None:
                break

            if review.approved and not current_wording_flags and not current_case_law_flags:
                converged = True
                break

        counsel_checklist = self._build_counsel_checklist(
            request, all_wording_flags, all_case_law_flags, veto_reason
        )

        output_with_banners = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "proposed_decision": request.proposed_decision,
            "wording_flags": list(dict.fromkeys(all_wording_flags)),
            "case_law_flags": list(dict.fromkeys(all_case_law_flags)),
            "counsel_checklist": counsel_checklist,
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
        wording_flags: list[str], case_law_flags: list[str]
    ) -> str:
        if not wording_flags and not case_law_flags:
            return ""
        parts: list[str] = []
        if wording_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(wording_flags)
            )
            parts.append(
                "⚠️  WORDING FLAGS (quote the controlling clause verbatim and re-map "
                "the loss mechanism):\n"
                f"{flags_text}"
            )
        if case_law_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(case_law_flags)
            )
            parts.append(
                "⚠️  CASE-LAW FLAGS (replace the authority with in-jurisdiction, "
                "current, on-point precedent):\n"
                f"{flags_text}"
            )
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _compose_output(draft: str, veto_reason: str | None) -> str:
        if veto_reason is None:
            return f"{draft}\n\n---\n\n{_DISCLAIMER}"
        return f"{draft}\n\n---\n\n{_VETO_BANNER}\n\n{_DISCLAIMER}"

    @staticmethod
    def _build_counsel_checklist(
        request: CoverageDecisionRequest,
        wording_flags: list[str],
        case_law_flags: list[str],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = []
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — escalate to coverage counsel BEFORE any "
                "communication to the insured; do not send this decision"
            )
        if wording_flags:
            checklist.append(
                f"[ ] ⚠️  WORDING FLAGS DETECTED ({len(wording_flags)}) — pull the "
                "actual policy form and re-quote the controlling clause"
            )
        if case_law_flags:
            checklist.append(
                f"[ ] ⚠️  CASE-LAW FLAGS DETECTED ({len(case_law_flags)}) — "
                "re-Shepardize cited authority in the governing jurisdiction"
            )
        checklist.extend([
            "[ ] Coverage counsel review for any denial or partial-coverage decision",
            "[ ] Draft reservation-of-rights letter if coverage is contested",
            "[ ] Confirm state-mandated response window and calendar the deadline",
            "[ ] Bad-faith file review (delay log, lowball history, surplus-lines flag)",
            f"[ ] Confirm proposed decision matches authority level: {request.proposed_decision[:50]}",
            "[ ] Issue decision — AI output must not trigger automatic denial",
        ])
        return checklist
