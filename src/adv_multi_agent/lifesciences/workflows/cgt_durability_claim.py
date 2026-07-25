"""
Workflow — CGT Durability / Curative Claim Substantiation Review (Lifesciences ·
Advanced Therapies / CGT, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to a proposed
durability / curative labeling claim for a one-time cell or gene therapy:
executor drafts the claim; reviewer (cross-model per ARIS §2.1) challenges a
durability claim that exceeds the observed follow-up, follow-up evidence
insufficient to support persistence of effect, and "cure" language unsupported by
the endpoint, with the power to VETO when the claim overstates benefit enough to
create patient-harm / misbranding exposure.

Boundary (D-LIFESCI-2): distinct from PromotionalOffLabelReviewWorkflow, which
reviews marketing copy against an already-approved label. This substantiates a
pre-approval clinical / labeling claim against long-term follow-up data.

Veto gate (D-LIFESCI-8): fires when the durability / curative claim is unsupported
by the follow-up duration and data — an overstatement with patient-harm /
misbranding exposure.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Clinical-study database (long-term follow-up) — durability data should
       resolve against the controlled LTFU clinical-study database.
    2. Efficacy / durability registry — persistence-of-effect data should
       reconcile against the controlled durability registry.
    3. Labeling-management system — the claim must map into the controlled
       labeling-management system before any use.
    4. Biostatistics analysis dataset — censoring and follow-up statistics should
       resolve against the controlled analysis dataset.
    5. Qualified approver gate — every AI-suggested claim conclusion must be
       confirmed by a qualified Regulatory Affairs + Medical Affairs reviewer.
       Output is never a filed labeling claim.
    6. Dedicated third-model claim auditor — production should use a separately
       configured auditor model for claim-inflation bias detection. See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import (
    extract_flags,
    extract_veto_directive,
    sanitize_for_prompt,
    sanitize_request_text,
    truncate_flag_display,
)
from ...core.workflow import BaseWorkflow, WorkflowResult

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated durability / curative claim substantiation "
    "review is decision-support, not an approved labeling claim and not a "
    "regulatory submission. A qualified Regulatory Affairs + Medical Affairs "
    "reviewer must independently confirm the durability and curative claims "
    "against the long-term follow-up data before any use. Not legal or medical "
    "advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found the "
    "durability / curative claim unsupported by the follow-up duration and data; "
    "making it would overstate benefit with patient-harm / misbranding exposure. "
    "See metadata['veto_reason']. Escalate to Regulatory Affairs + Medical Affairs."
)

_FLAG_HEADERS = ("DURABILITY-CLAIM FLAGS:", "FOLLOWUP-EVIDENCE FLAGS:", "CURATIVE-LANGUAGE FLAGS:")

_DURABILITY_REVIEW_CRITERIA = """\
Evaluate this durability / curative claim substantiation review on five dimensions.
Score each 0–10.

1. DURABILITY vs FOLLOW-UP DURATION (30%) — CRITICAL
   Does the durability claim stay within the observed follow-up duration and
   censoring? Penalise a claim that extends beyond the data. Flag under
   DURABILITY-CLAIM FLAGS:.

2. FOLLOW-UP EVIDENCE SUFFICIENCY (25%) — CRITICAL
   Are the n, median follow-up, and loss-of-response data sufficient to support
   the claimed persistence of effect? Penalise insufficient follow-up evidence.
   Flag under FOLLOWUP-EVIDENCE FLAGS:.

3. CURATIVE LANGUAGE (20%) — CRITICAL
   Is any "cure" / permanent-benefit language supported by the endpoint and data?
   Penalise curative language the endpoint cannot support. Flag under
   CURATIVE-LANGUAGE FLAGS:.

4. COMPARATOR / NATURAL-HISTORY CONTEXT (15%)
   Is the claim contextualised against a comparator or natural history? Penalise a
   claim with no comparator context where one is needed.

5. ACTIONABILITY (10%)
   Is each finding specific enough for Medical / Regulatory to resolve (which
   claim, which follow-up window, which endpoint)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the durability / curative claim is unsupported by the follow-up
duration and data — an overstatement with patient-harm / misbranding exposure.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero DURABILITY-CLAIM FLAGS AND zero FOLLOWUP-EVIDENCE FLAGS AND
zero CURATIVE-LANGUAGE FLAGS AND no VETO: ready for Regulatory + Medical sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  DURABILITY-CLAIM FLAGS: [bullet list, or "None detected"]
  FOLLOWUP-EVIDENCE FLAGS: [bullet list, or "None detected"]
  CURATIVE-LANGUAGE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are substantiating a proposed durability / curative labeling claim for a
one-time cell or gene therapy for a qualified Regulatory Affairs + Medical Affairs
reviewer. You have no stake in the outcome. Assess whether the claim is supported
by the long-term follow-up data, grounded only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

DURABILITY-CLAIM DATA:
{request_text}

{wiki_context}

Produce a structured review with exactly these sections:

## Durability vs follow-up
State whether the durability claim stays within the observed follow-up and
censoring; identify any claim beyond the data.

## Follow-up evidence
State whether n, median follow-up, and loss-of-response support the claimed
persistence of effect.

## Curative language
State whether any curative / permanent-benefit language is supported by the
endpoint.

## Comparator / natural-history context
State whether the claim is contextualised against a comparator or natural history.

## Claim conclusion
State whether the durability / curative claim is supported, or whether it
overstates benefit.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this durability / curative claim substantiation review. Address EVERY issue
in the reviewer's critique, especially any DURABILITY-CLAIM FLAGS, FOLLOWUP-EVIDENCE
FLAGS, or CURATIVE-LANGUAGE FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any DURABILITY-CLAIM flag: narrow the durability claim to the observed
follow-up window, or acknowledge it is unsupported.
⚠️  For any FOLLOWUP-EVIDENCE flag: cite the follow-up n / duration that supports
persistence, or acknowledge the evidence is insufficient.
⚠️  For any CURATIVE-LANGUAGE flag: remove or qualify curative language the
endpoint cannot support.
"""


@dataclass
class DurabilityClaimRequest:
    """Structured input for the CGT durability / curative claim substantiation review."""

    product_description: str
    """Generic product category (e.g. a one-time AAV gene therapy)."""

    proposed_claim: str
    """The proposed durability / curative labeling claim."""

    pivotal_efficacy_summary: str
    """Pivotal efficacy result summary."""

    followup_duration_and_n: str
    """Follow-up duration, median follow-up, and n (with censoring)."""

    durability_evidence: str
    """Durability evidence: loss-of-response, redosing, persistence."""

    population_and_endpoint: str
    """Study population and the endpoint the claim rests on."""

    comparator_or_natural_history: str
    """Comparator or natural-history context for the claim."""

    label_context: str
    """Where the claim would appear in the label / communication."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Proposed claim: {self.proposed_claim[:cap]}",
            f"Pivotal efficacy summary: {self.pivotal_efficacy_summary[:cap]}",
            f"Follow-up duration and n: {self.followup_duration_and_n[:cap]}",
            f"Durability evidence: {self.durability_evidence[:cap]}",
            f"Population and endpoint: {self.population_and_endpoint[:cap]}",
            f"Comparator / natural history: {self.comparator_or_natural_history[:cap]}",
            f"Label context: {self.label_context[:cap]}",
        ])


class CGTDurabilityClaimWorkflow(BaseWorkflow):
    """
    Adversarial CGT durability / curative claim substantiation review: executor
    drafts the claim → reviewer challenges a durability claim beyond the follow-up,
    insufficient follow-up evidence, and unsupported curative language, with the
    power to VETO → iterate.

    Convergence gate (D-LIFESCI-8):
        score ≥ threshold (8.0)
        AND zero DURABILITY-CLAIM FLAGS
        AND zero FOLLOWUP-EVIDENCE FLAGS
        AND zero CURATIVE-LANGUAGE FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the wiki.
    The verbatim veto directive is recorded in metadata['veto_reason'];
    metadata['first_draft'] captures the clean executor draft from the vetoed round.
    """

    async def run(  # type: ignore[override]
        self,
        request: DurabilityClaimRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_request_text(request)
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
                criteria=_DURABILITY_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            veto_reason = self._extract_veto(review.critique, max_wiki_chars)
            if veto_reason is not None:
                break

            if review.approved and not self._flag_classes_unresolved(
                review.critique, _FLAG_HEADERS, current.values()
            ):
                converged = True
                break

        durability_checklist = self._build_durability_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "durability_claim_flags": list(dict.fromkeys(accumulated["DURABILITY-CLAIM FLAGS:"])),
            "followup_evidence_flags": list(
                dict.fromkeys(accumulated["FOLLOWUP-EVIDENCE FLAGS:"])
            ),
            "curative_language_flags": list(
                dict.fromkeys(accumulated["CURATIVE-LANGUAGE FLAGS:"])
            ),
            "durability_checklist": durability_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
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
        """Thin delegate to `core._internal.extract_veto_directive` (M-PC-1)."""
        return extract_veto_directive(critique, "REVIEWER VETO:", max_chars)

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "DURABILITY-CLAIM FLAGS:": (
                "⚠️  DURABILITY-CLAIM FLAGS (narrow the durability claim to the observed "
                "follow-up window, or acknowledge it is unsupported):"
            ),
            "FOLLOWUP-EVIDENCE FLAGS:": (
                "⚠️  FOLLOWUP-EVIDENCE FLAGS (cite the follow-up n / duration that "
                "supports persistence, or acknowledge insufficient evidence):"
            ),
            "CURATIVE-LANGUAGE FLAGS:": (
                "⚠️  CURATIVE-LANGUAGE FLAGS (remove or qualify curative language the "
                "endpoint cannot support):"
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
    def _build_durability_checklist(
        request: DurabilityClaimRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Regulatory Affairs + Medical Affairs]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — do not make the durability / curative claim; "
                "escalate to Regulatory Affairs + Medical Affairs and narrow the claim "
                "to the supported follow-up window"
            )
        durability_flags = accumulated.get("DURABILITY-CLAIM FLAGS:", [])
        followup_flags = accumulated.get("FOLLOWUP-EVIDENCE FLAGS:", [])
        curative_flags = accumulated.get("CURATIVE-LANGUAGE FLAGS:", [])
        if durability_flags:
            checklist.append(
                f"[ ] ⚠️  DURABILITY-CLAIM FLAGS ({len(durability_flags)}) — narrow "
                "each durability claim to the observed follow-up window"
            )
        if followup_flags:
            checklist.append(
                f"[ ] ⚠️  FOLLOWUP-EVIDENCE FLAGS ({len(followup_flags)}) — supply the "
                "follow-up evidence that supports persistence"
            )
        if curative_flags:
            checklist.append(
                f"[ ] ⚠️  CURATIVE-LANGUAGE FLAGS ({len(curative_flags)}) — remove or "
                "qualify each unsupported curative statement"
            )
        checklist.extend([
            "[ ] Confirm the durability claim stays within the observed follow-up",
            "[ ] Confirm follow-up n and duration support persistence of effect",
            "[ ] Confirm curative language is supported by the endpoint",
            "[ ] Obtain Regulatory Affairs + Medical Affairs sign-off before any use",
        ])
        return checklist
