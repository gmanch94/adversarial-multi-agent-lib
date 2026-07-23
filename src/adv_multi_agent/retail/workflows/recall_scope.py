"""
Workflow — Food Recall Scope (Retail Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for retail food-safety
recall scoping. Executor drafts a recall plan; reviewer (recommended:
different model family per ARIS §2.1 principle 1) challenges scope, evidence,
and regulatory fit, and can issue a REVIEWER VETO that halts the workflow.

This workflow uses the **reviewer-veto** pattern (D-RETAIL-1): the
reviewer can issue a verbatim VETO directive under `REVIEWER VETO:` to
halt the loop immediately. The decision is irreversible-class, mirrors
ARIS §3.2 cross-model audit, and is the strongest convergence gate
available — score and flag counts do not override a veto.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Lot traceability integration — supplier_lot is free-text; production
       requires integration with traceability systems (e.g. GS1 EPCIS) so
       lot-to-store mapping is authoritative, not inferred by an LLM.
    2. Regulatory directive API — FDA / USDA / state agency directives
       should be pulled from a structured feed, not paraphrased into
       caller-supplied text.
    3. Lab confirmation gate — recall scope must be backed by primary
       evidence (pathogen positive lab result, regulatory order). LLM
       output alone is not actionable.
    4. Safety officer + legal + comms sign-off — recall publication is
       irreversible. AI output is advisory; sign-off is human-only.
    5. Append-only audit store — every recall draft, flag, and veto must
       be captured in a tamper-evident store for after-the-fact review by
       regulators. The in-memory ledger here is a teaching simulation.
    6. Dedicated third-model safety auditor — this workflow folds the
       scope audit into the same reviewer that scores quality. Production
       should run a separately configured model (different family from
       BOTH executor and reviewer) whose only job is recall-scope
       verification against primary evidence. See ARIS §3.1.
    7. Customer-exposure model — consumer_exposure is free-text; production
       requires a structured loyalty / POS query to count units sold and
       (where consented) reach customers directly.
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

# L-PC-3: per-field cap — prevents a single oversized field crowding out
# later fields when the concatenated prompt is trimmed by sanitize_for_prompt.
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated recall plan is not an authorised "
    "recall directive. A human safety officer must verify scope against "
    "primary evidence (lab confirmation, regulatory order) and obtain "
    "safety / legal / communications sign-off before any consumer-facing "
    "action. AI output must never trigger an automated recall."
)

_VETO_BANNER = (
    "⚠️  REVIEWER VETO — workflow halted before convergence. "
    "See metadata['veto_reason']. Escalate to safety officer immediately."
)

_RECALL_REVIEW_CRITERIA = """\
Evaluate this recall plan on five dimensions. Score each 0–10.

1. SCOPE ACCURACY (30%) — CRITICAL
   Is the recall scope (lots, SKUs, stores, date window) traceable to the
   stated contamination signal and supplier_lot evidence? Penalise scope
   that is too narrow (missed lots, missed stores, missed dates) OR too
   broad (unjustified scope expansion creates supplier-relations risk and
   waste). Flag every gap under SCOPE FLAGS:.

2. EVIDENCE GROUNDING (25%) — CRITICAL
   Is the recall scoped against primary evidence (lab confirmation,
   regulatory directive, traceable lot match) — not against a single
   customer complaint or a hand-wavy signal? Flag every unsupported
   scope decision under EVIDENCE FLAGS:.

3. REGULATORY FIT (20%)
   Does the plan meet the obligations stated in regulatory_context (e.g.
   21 CFR Part 7 reportable-recall criteria, state notification timelines)?
   Penalise plans that miss a regulator notification or a required
   public-warning step.

4. CONSUMER EXPOSURE (15%)
   Are units sold and reachable customers identified? Is the communications
   approach (press release, in-store signage, direct loyalty outreach)
   matched to the exposure level?

5. ACTIONABILITY (10%)
   Are the immediate halt-sale, pull-from-shelf, and notification actions
   specific enough for a safety officer to execute? Are owners named?

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Life-safety pathogen signal (E. coli O157:H7, Listeria, Salmonella with
    severity, botulism, undeclared major allergen) but no regulatory
    contact has been initiated.
  • Recall plan halts sale but does NOT pull stock already on shelves.
  • Consumer exposure is non-zero but no consumer notification path is
    proposed.
  • Recall plan proposes downgrading scope below primary evidence (e.g.
    plan recalls one lot when lab match covers multiple).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those
  as stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score ≥ 7.5 AND zero SCOPE FLAGS AND zero EVIDENCE FLAGS AND no VETO:
plan is ready for safety-officer review.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SCOPE FLAGS: [bullet list, or "None detected"]
  EVIDENCE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are preparing a food-safety recall plan for a human safety officer to review.
You have no stake in the outcome. Your job is to scope the recall so it matches
the primary evidence — not to minimise commercial impact, not to maximise caution.

BASE SCOPE DECISIONS ON THE INPUT DATA. Do not import assumptions from general
food-safety practice that are not grounded in the specific contamination signal,
supplier lots, distribution window, and regulatory context below.

INCIDENT DATA:
{request_text}

{wiki_context}

Produce a structured recall plan with exactly these sections:

## Contamination Signal Summary
Restate the contamination signal in one paragraph. Identify the pathogen /
defect, severity, and source of the signal (lab result, complaint, supplier
notification, regulatory directive). Note any competing or conflicting
evidence.

## Recall Scope
Specify exactly: lots affected, SKUs affected, store list, distribution
date window, expected number of units. Trace each scope decision back to
a specific input field.

## Evidence Basis
For each scope decision (lot, store, date), state the primary evidence
that supports it. If a scope decision rests on inference rather than
primary evidence, say so explicitly.

## Regulatory Actions
List required notifications: agency, contact, deadline (per
regulatory_context). State whether a public warning is required.

## Consumer Communications
Channels and content for consumer notification: press release scope,
in-store signage, direct loyalty outreach (for known purchasers), recall
hotline. Match channel intensity to consumer_exposure.

## Operational Actions
Immediate halt-sale order, pull-from-shelf instructions to stores, hold-at-
DC instructions, return-to-supplier or destruction instructions.

## Evidence Gaps
Information missing from the inputs that materially affects scope
accuracy or regulatory fit. Note the gap impact.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this recall plan. Address EVERY issue in the reviewer's critique,
especially any SCOPE FLAGS or EVIDENCE FLAGS.

PREVIOUS PLAN:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SCOPE FLAG: expand or contract scope to match the primary
evidence — do not paper over the gap.
⚠️  For any EVIDENCE FLAG: either cite the primary evidence in the input
data, or remove the unsupported scope decision.
"""


@dataclass
class RecallRequest:
    """Structured input for the food-recall scope workflow."""

    contamination_signal: str
    """Pathogen / supplier alert / customer complaint summary."""

    supplier_lot: str
    """Lot codes implicated (free text; production would be GS1 EPCIS lookup)."""

    product_skus: str
    """SKUs affected."""

    distribution_window: str
    """Production + ship dates for the implicated lots."""

    stores_in_scope: str
    """Store IDs receiving the lot."""

    consumer_exposure: str
    """Units sold to date; reachable customer demographics if known."""

    regulatory_context: str
    """FDA / USDA / state-agency notification requirements and deadlines."""

    competing_evidence: str
    """Conflicting signals (negative lab results, supplier denials, alternative
    explanations) that the reviewer must weigh against the primary signal."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Contamination signal: {self.contamination_signal[:cap]}",
            f"Supplier lot: {self.supplier_lot[:cap]}",
            f"Product SKUs: {self.product_skus[:cap]}",
            f"Distribution window: {self.distribution_window[:cap]}",
            f"Stores in scope: {self.stores_in_scope[:cap]}",
            f"Consumer exposure: {self.consumer_exposure[:cap]}",
            f"Regulatory context: {self.regulatory_context[:cap]}",
            f"Competing evidence: {self.competing_evidence[:cap]}",
        ])


class RecallScopeWorkflow(BaseWorkflow):
    """
    Adversarial food-recall scoping: executor drafts plan → reviewer
    challenges scope + evidence + may VETO → iterate.

    Convergence gate (D-RETAIL-1):
        score ≥ threshold
        AND zero SCOPE FLAGS
        AND zero EVIDENCE FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately, recording the verbatim veto
    directive in metadata['veto_reason']. Score and flags from the vetoed
    round are also captured. The output banner directs the safety officer
    to escalate.
    """

    async def run(  # type: ignore[override]
        self,
        request: RecallRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial recall-scope loop."""
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_scope_flags: list[str] = []
        current_evidence_flags: list[str] = []
        all_scope_flags: list[str] = []
        all_evidence_flags: list[str] = []
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
                    current_scope_flags, current_evidence_flags
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
                criteria=_RECALL_REVIEW_CRITERIA,
            )
            score = review.score
            current_scope_flags = extract_flags(review.critique, "SCOPE FLAGS:")
            current_evidence_flags = extract_flags(review.critique, "EVIDENCE FLAGS:")
            all_scope_flags.extend(current_scope_flags)
            all_evidence_flags.extend(current_evidence_flags)

            # Audit-trail writes happen BEFORE the veto check (veto is a halt,
            # not a rollback — what was vetoed and why must be recorded).
            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            veto_reason = self._extract_veto(review.critique, max_wiki_chars)
            if veto_reason is not None:
                break

            if review.approved and not current_scope_flags and not current_evidence_flags:
                converged = True
                break

        safety_checklist = self._build_safety_checklist(
            request, all_scope_flags, all_evidence_flags, veto_reason
        )

        output_with_banners = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "supplier_lot": sanitize_for_prompt(request.supplier_lot, max_chars=200),
            "scope_flags": list(dict.fromkeys(all_scope_flags)),
            "evidence_flags": list(dict.fromkeys(all_evidence_flags)),
            "safety_checklist": safety_checklist,
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
        """Return the verbatim veto directive, or None if not vetoed.

        Thin delegate to `core._internal.extract_veto_directive`, which
        applies the M-PC-1 line-anchored marker match + M2 continuation
        + L5 sibling-header hardening uniformly across every veto-using
        workflow. Test API preserved.
        """
        return extract_veto_directive(critique, "REVIEWER VETO:", max_chars)

    @staticmethod
    def _format_flag_section(
        scope_flags: list[str], evidence_flags: list[str]
    ) -> str:
        if not scope_flags and not evidence_flags:
            return ""
        parts: list[str] = []
        if scope_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(scope_flags)
            )
            parts.append(
                "⚠️  SCOPE FLAGS (expand or contract scope to match evidence):\n"
                f"{flags_text}"
            )
        if evidence_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(evidence_flags)
            )
            parts.append(
                "⚠️  EVIDENCE FLAGS (cite primary evidence or remove the scope decision):\n"
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
    def _build_safety_checklist(
        request: RecallRequest,
        scope_flags: list[str],
        evidence_flags: list[str],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = []
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — escalate to safety officer BEFORE any "
                "consumer-facing action; do not publish this draft"
            )
        if scope_flags:
            checklist.append(
                f"[ ] ⚠️  SCOPE FLAGS DETECTED ({len(scope_flags)}) — verify "
                "scope against lot traceability records before recall publish"
            )
        if evidence_flags:
            checklist.append(
                f"[ ] ⚠️  EVIDENCE FLAGS DETECTED ({len(evidence_flags)}) — "
                "obtain primary evidence (lab confirm or regulatory order) "
                "before recall publish"
            )
        checklist.extend([
            f"[ ] Confirm lot {request.supplier_lot} against GS1 / EPCIS traceability records",
            "[ ] Obtain primary evidence: lab confirmation OR regulatory directive",
            "[ ] Notify FDA / USDA per stated regulatory_context deadlines",
            "[ ] Issue halt-sale to all stores in scope; confirm pull-from-shelf",
            "[ ] Draft + sign-off consumer notification (press, signage, loyalty outreach)",
            "[ ] Sign-off chain: safety officer + legal + comms director",
            "[ ] Re-audit recall scope every 24h until incident closed",
            "[ ] Publish recall — AI output must not trigger automatic recall notice",
        ])
        return checklist
