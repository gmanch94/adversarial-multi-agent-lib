"""
Workflow — CCDS Safety Label Change Review (Lifesciences · Pharma, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to a Company Core Data
Sheet (CCDS) safety label change: executor evaluates the downstream implementation
of a safety-labeling change across regions and the regulatory clock, given an
already-established signal; reviewer (cross-model per ARIS §2.1) challenges a label
change that understates the signal, a regional divergence, and a missed
notification clock, with the power to VETO a change that fails to convey an
established serious risk on time.

BOUNDARY (D-LIFESCI-2): distinct from the lifesciences
PharmacovigilanceSignalWorkflow — that detects and validates an aggregate safety
SIGNAL and its labeling implication; this evaluates the downstream IMPLEMENTATION
of a CCDS safety label change across regions and the regulatory clock, given an
already-established signal. Input is the summarized signal + proposed label text +
regional divergence, NOT raw case-level narratives (those are the PV-signal
workflow's concern).

Veto gate (D-LIFESCI-4): fires when a CCDS/label-change plan omits or materially
understates an established serious safety signal in the safety labeling, OR misses
a mandatory regulatory notification clock for a safety change.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Global-labeling / CCDS management system — the CCDS and its change should
       resolve against the controlled labeling system, not caller-pasted text.
    2. Regulatory-submission tracking (per-region clocks) — the notification /
       submission timelines should resolve against the controlled submission-
       tracking system.
    3. Safety-signal-management system (upstream) — the established signal should
       resolve against the controlled signal-management system.
    4. Local-label impact-assessment tooling — the regional-divergence analysis
       should resolve against the controlled local-label impact system.
    5. Qualified approver gate — every AI-suggested label change must be reviewed
       by a qualified Global Labeling / Regulatory Affairs lead. Output is never an
       auto-implemented label change.
    6. Dedicated third-model labeling auditor — production should use a separately
       configured auditor model for signal-to-label fidelity bias detection.
       See ARIS §3.1.
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

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated CCDS safety label-change review is "
    "decision-support, not a labeling decision and not a regulatory submission. A "
    "qualified Global Labeling / Regulatory Affairs approver must independently "
    "confirm the signal-to-label fidelity, regional consistency, and notification "
    "timelines before any label change is implemented. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "CCDS/label-change plan that fails to convey an established serious risk or "
    "misses a mandatory safety-labeling clock. See metadata['veto_reason']. "
    "Escalate to Global Labeling / Regulatory Affairs; the label change must not "
    "proceed as drafted."
)

_FLAG_HEADERS = (
    "SAFETY-SIGNAL FLAGS:",
    "REGIONAL-DIVERGENCE FLAGS:",
    "IMPLEMENTATION-CLOCK FLAGS:",
)

_CCDS_REVIEW_CRITERIA = """\
Evaluate this CCDS safety label-change review on five dimensions. Score each 0–10.

1. SIGNAL-TO-LABEL FIDELITY (30%) — CRITICAL
   Does the proposed CCDS wording convey the established safety signal faithfully,
   with no safety implication understated or omitted? Penalise wording that
   understates the signal. Flag under SAFETY-SIGNAL FLAGS:.

2. REGIONAL CONSISTENCY (25%) — CRITICAL
   Does every regional/local label reflect the CCDS change, with any divergence
   justified and no market missed? Penalise an unjustified divergence or a missed
   market. Flag under REGIONAL-DIVERGENCE FLAGS:.

3. TIMELINE COMPLIANCE (20%) — CRITICAL
   Does the plan meet every mandatory regulatory notification/submission clock for
   the safety change? Penalise a timeline the plan will miss. Flag under
   IMPLEMENTATION-CLOCK FLAGS:.

4. BENEFIT-RISK COHERENCE (15%)
   Is the wording proportionate to the signal and the population-level
   benefit-risk? Penalise wording out of proportion to the signal.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which wording, which region, which
   clock)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the plan omits or materially understates an established serious
safety signal in the safety labeling, OR misses a mandatory regulatory
notification clock for a safety change. Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SAFETY-SIGNAL FLAGS AND zero REGIONAL-DIVERGENCE FLAGS AND
zero IMPLEMENTATION-CLOCK FLAGS AND no VETO: ready for Global Labeling sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SAFETY-SIGNAL FLAGS: [bullet list, or "None detected"]
  REGIONAL-DIVERGENCE FLAGS: [bullet list, or "None detected"]
  IMPLEMENTATION-CLOCK FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are reviewing a CCDS safety label-change implementation for a Global Labeling
/ Regulatory Affairs approver. You have no stake in the outcome. Given an
already-established safety signal, assess whether the proposed CCDS wording is
faithful, whether regional labels are consistent, and whether the plan meets the
notification clocks — grounded only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

CCDS LABEL-CHANGE DATA:
{request_text}

{wiki_context}

Produce a structured review with exactly these sections:

## Signal-to-label fidelity
State whether the proposed CCDS wording conveys the established signal faithfully.
Do not accept wording that understates the signal.

## Regional consistency
State whether every regional/local label reflects the change, and whether any
divergence is justified or a market is missed.

## Timeline compliance
State whether the plan meets every mandatory notification/submission clock.

## Benefit-risk and disposition
State whether the wording is proportionate to the signal and whether the change
may proceed.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this CCDS safety label-change review. Address EVERY issue in the reviewer's
critique, especially any SAFETY-SIGNAL FLAGS, REGIONAL-DIVERGENCE FLAGS, or
IMPLEMENTATION-CLOCK FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SAFETY-SIGNAL flag: convey the established signal faithfully; do not understate it.
⚠️  For any REGIONAL-DIVERGENCE flag: reconcile the region or justify the divergence.
⚠️  For any IMPLEMENTATION-CLOCK flag: correct the plan to meet the mandatory clock.
"""


@dataclass
class CCDSLabelChangeRequest:
    """Structured input for the CCDS safety label-change review workflow.

    Inputs are the SUMMARIZED signal + proposed label text + regional divergence,
    NOT raw case-level narratives (those belong to PharmacovigilanceSignalWorkflow).
    """

    product_description: str
    """Generic product category."""

    safety_signal_summary: str
    """The established / validated signal driving the change (summarized)."""

    proposed_ccds_change: str
    """The proposed CCDS safety-section wording change."""

    current_ccds_text: str
    """Current relevant CCDS wording."""

    regional_label_status: str
    """How the change maps to regional labels (divergence)."""

    regulatory_timelines: str
    """Applicable notification / submission clocks per region."""

    implementation_plan: str
    """Rollout across markets and local-label updates."""

    benefit_risk_context: str
    """Population-level benefit-risk framing."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Safety signal summary: {self.safety_signal_summary[:cap]}",
            f"Proposed CCDS change: {self.proposed_ccds_change[:cap]}",
            f"Current CCDS text: {self.current_ccds_text[:cap]}",
            f"Regional label status: {self.regional_label_status[:cap]}",
            f"Regulatory timelines: {self.regulatory_timelines[:cap]}",
            f"Implementation plan: {self.implementation_plan[:cap]}",
            f"Benefit-risk context: {self.benefit_risk_context[:cap]}",
        ])


class CCDSLabelChangeWorkflow(BaseWorkflow):
    """
    Adversarial CCDS safety label-change review: executor evaluates the downstream
    implementation of a safety-labeling change → reviewer challenges an understated
    signal, a regional divergence, and a missed notification clock, with the power
    to VETO → iterate.

    BOUNDARY (D-LIFESCI-2): distinct from the lifesciences
    PharmacovigilanceSignalWorkflow — that detects and validates an aggregate
    safety signal; this evaluates the downstream IMPLEMENTATION of a CCDS label
    change across regions and the regulatory clock, given an established signal.

    Convergence gate (D-LIFESCI-4):
        score ≥ threshold (8.0)
        AND zero SAFETY-SIGNAL FLAGS
        AND zero REGIONAL-DIVERGENCE FLAGS
        AND zero IMPLEMENTATION-CLOCK FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: CCDSLabelChangeRequest,
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
                flag_section = self._format_flag_section(current)
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
                criteria=_CCDS_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            # Audit-trail write happens BEFORE the veto check (D-LIFESCI-4).
            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            veto_reason = self._extract_veto(review.critique, max_wiki_chars)
            if veto_reason is not None:
                break

            if review.approved and not any(current.values()):
                converged = True
                break

        ccds_checklist = self._build_ccds_checklist(request, accumulated, veto_reason)

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "safety_signal_flags": list(
                dict.fromkeys(accumulated["SAFETY-SIGNAL FLAGS:"])
            ),
            "regional_divergence_flags": list(
                dict.fromkeys(accumulated["REGIONAL-DIVERGENCE FLAGS:"])
            ),
            "implementation_clock_flags": list(
                dict.fromkeys(accumulated["IMPLEMENTATION-CLOCK FLAGS:"])
            ),
            "ccds_checklist": ccds_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the approver sees what the AI produced before the REVIEWER VETO
            # banner was prepended. (Input is aggregate signal + label text, not
            # case-level narratives, so no patient-PHI caveat applies here.)
            metadata["first_draft"] = output

        return WorkflowResult(
            output=output_with_banner,
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
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "SAFETY-SIGNAL FLAGS:": (
                "⚠️  SAFETY-SIGNAL FLAGS (convey the established signal faithfully; "
                "do not understate it):"
            ),
            "REGIONAL-DIVERGENCE FLAGS:": (
                "⚠️  REGIONAL-DIVERGENCE FLAGS (reconcile the region or justify the "
                "divergence):"
            ),
            "IMPLEMENTATION-CLOCK FLAGS:": (
                "⚠️  IMPLEMENTATION-CLOCK FLAGS (correct the plan to meet the "
                "mandatory clock):"
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
    def _compose_output(draft: str, veto_reason: str | None) -> str:
        if veto_reason is None:
            return f"{draft}\n\n---\n\n{_DISCLAIMER}"
        return (
            f"{_VETO_BANNER}\n\nVETO DIRECTIVE: {veto_reason}\n\n"
            f"--- Vetoed draft below ---\n\n{draft}\n\n---\n\n{_DISCLAIMER}"
        )

    @staticmethod
    def _build_ccds_checklist(
        request: CCDSLabelChangeRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Global Labeling / Regulatory Affairs]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — the label change fails to convey an "
                "established serious risk or misses a mandatory safety-labeling "
                "clock; escalate to Global Labeling and do not proceed as drafted"
            )
        signal_flags = accumulated.get("SAFETY-SIGNAL FLAGS:", [])
        regional_flags = accumulated.get("REGIONAL-DIVERGENCE FLAGS:", [])
        clock_flags = accumulated.get("IMPLEMENTATION-CLOCK FLAGS:", [])
        if signal_flags:
            checklist.append(
                f"[ ] ⚠️  SAFETY-SIGNAL FLAGS ({len(signal_flags)}) — convey the "
                "established signal faithfully in the wording"
            )
        if regional_flags:
            checklist.append(
                f"[ ] ⚠️  REGIONAL-DIVERGENCE FLAGS ({len(regional_flags)}) — "
                "reconcile each region or justify the divergence"
            )
        if clock_flags:
            checklist.append(
                f"[ ] ⚠️  IMPLEMENTATION-CLOCK FLAGS ({len(clock_flags)}) — correct "
                "the plan to meet each mandatory notification clock"
            )
        checklist.extend([
            "[ ] Confirm the CCDS wording conveys the established signal faithfully",
            "[ ] Confirm every regional label reflects the change or justifies divergence",
            "[ ] Confirm the plan meets every mandatory safety-labeling clock",
            "[ ] Obtain Global Labeling / Regulatory Affairs sign-off before implementation",
        ])
        return checklist
