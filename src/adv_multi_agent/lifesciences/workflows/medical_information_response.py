"""
Workflow — Medical Information Response Review (Lifesciences · Pharma, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to a reactive medical-
information response: executor drafts/reviews a response to an unsolicited medical
inquiry (off-label boundary, fair balance, evidence calibration); reviewer
(cross-model per ARIS §2.1) challenges any off-label statement that crosses into
promotion, missing fair balance, and over-stated claims, with the power to VETO a
response that promotes an unapproved use.

BOUNDARY (D-LIFESCI-2): distinct from the lifesciences
PromotionalOffLabelReviewWorkflow — that reviews PROACTIVE promotional material,
where off-label promotion is prohibited; this drafts a REACTIVE response to an
unsolicited medical inquiry, where a truthful, balanced, non-promotional
scientific exchange (including off-label information) is permitted. The veto here
fires only when the reactive response crosses into PROMOTION of an off-label use.

Veto gate (D-LIFESCI-4): fires when a response crosses from a truthful, balanced,
reactive scientific exchange into PROMOTION of an off-label use.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Medical-information management system + standard-response-document library
       — the response should resolve against the controlled medical-information
       system and approved response library, not caller-pasted text.
    2. Literature database — the cited evidence should resolve against the
       controlled literature database.
    3. MLR review system — the response must pass the controlled medical / legal /
       regulatory review workflow before it is sent.
    4. Adverse-event intake integration — inquiries can contain adverse events;
       these must be routed to pharmacovigilance, not handled here.
    5. Qualified approver gate — every AI-suggested response must be reviewed by
       qualified Medical Information / Medical Affairs. Output is never an
       auto-sent medical-information response.
    6. Dedicated third-model response auditor — production should use a separately
       configured auditor model for off-label-boundary bias detection.
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
    "ADVISORY ONLY — This AI-generated medical-information response review is "
    "decision-support, not a response of record. Qualified Medical Information / "
    "Medical Affairs must independently confirm the off-label boundary, fair "
    "balance, and evidence calibration, and route any adverse event to "
    "pharmacovigilance, before any response is sent. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "response that crosses into PROMOTION of an off-label use. See "
    "metadata['veto_reason']. Escalate to Medical Affairs / MLR; the response "
    "must not be sent as drafted because it promotes an off-label use."
)

_FLAG_HEADERS = ("OFF-LABEL FLAGS:", "BALANCE FLAGS:", "EVIDENCE-LEVEL FLAGS:")

_MEDINFO_REVIEW_CRITERIA = """\
Evaluate this medical-information response on five dimensions. Score each 0–10.

1. OFF-LABEL BOUNDARY (30%) — CRITICAL
   Does every off-label statement stay within a truthful, non-promotional,
   evidence-based answer to the SPECIFIC unsolicited question? Penalise an
   off-label statement that exceeds the question and crosses into promotion. Flag
   under OFF-LABEL FLAGS:.

2. FAIR BALANCE (25%) — CRITICAL
   Is efficacy presented with fair balance of risk and limitation? Penalise
   efficacy stated without the corresponding risk/limitation. Flag under
   BALANCE FLAGS:.

3. EVIDENCE CALIBRATION (20%) — CRITICAL
   Is every claim stated no more strongly than its evidence level supports?
   Penalise a claim stronger than its evidence. Flag under EVIDENCE-LEVEL FLAGS:.

4. RESPONSIVENESS / NON-PROMOTIONAL TONE (15%)
   Does the response answer the actual question in a scientific, non-promotional
   tone? Penalise a response that is unresponsive or promotional in tone.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which statement, which risk, which
   claim)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the response crosses from a truthful, balanced, reactive
scientific exchange into PROMOTION of an off-label use. Otherwise:
"REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero OFF-LABEL FLAGS AND zero BALANCE FLAGS AND zero
EVIDENCE-LEVEL FLAGS AND no VETO: ready for Medical Information sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  OFF-LABEL FLAGS: [bullet list, or "None detected"]
  BALANCE FLAGS: [bullet list, or "None detected"]
  EVIDENCE-LEVEL FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are reviewing a medical-information response for qualified Medical Information
/ Medical Affairs to approve. You have no stake in the outcome. This is a REACTIVE
response to an unsolicited inquiry; a truthful, balanced, non-promotional
scientific exchange (including off-label information) is permitted — but it must
not PROMOTE an unapproved use. Assess the off-label boundary, fair balance, and
evidence calibration — grounded only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

MEDICAL-INFORMATION DATA:
{request_text}

{wiki_context}

Produce a structured review with exactly these sections:

## Off-label boundary
State whether every off-label statement stays within a truthful, non-promotional
answer to the specific question, or crosses into promotion.

## Fair balance
State whether efficacy is presented with the corresponding risk and limitation.

## Evidence calibration
State whether each claim is calibrated to its evidence level.

## Responsiveness and disposition
State whether the response answers the actual question and may be sent (subject to
MLR). Note any adverse event that must be routed to pharmacovigilance.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this medical-information response review. Address EVERY issue in the
reviewer's critique, especially any OFF-LABEL FLAGS, BALANCE FLAGS, or
EVIDENCE-LEVEL FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any OFF-LABEL flag: keep the response reactive and non-promotional; do not promote an off-label use.
⚠️  For any BALANCE flag: present the corresponding risk/limitation alongside efficacy.
⚠️  For any EVIDENCE-LEVEL flag: state the claim no more strongly than its evidence supports.
"""


@dataclass
class MedicalInfoRequest:
    """Structured input for the medical-information response review workflow."""

    product_description: str
    """Generic product category."""

    inquiry_summary: str
    """The unsolicited question (may reference a specific patient case)."""

    inquiry_source: str
    """HCP / patient / unsolicited channel."""

    on_off_label_status: str
    """Whether the question concerns on- or off-label use."""

    proposed_response: str
    """The drafted response content."""

    evidence_cited: str
    """Data / references supporting the response."""

    balance_summary: str
    """How risks / limitations are presented alongside efficacy."""

    promotional_review_status: str
    """Whether the response has been kept non-promotional (MLR posture)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Inquiry summary: {self.inquiry_summary[:cap]}",
            f"Inquiry source: {self.inquiry_source[:cap]}",
            f"On/off-label status: {self.on_off_label_status[:cap]}",
            f"Proposed response: {self.proposed_response[:cap]}",
            f"Evidence cited: {self.evidence_cited[:cap]}",
            f"Balance summary: {self.balance_summary[:cap]}",
            f"Promotional review status: {self.promotional_review_status[:cap]}",
        ])


class MedicalInformationResponseWorkflow(BaseWorkflow):
    """
    Adversarial medical-information response review: executor reviews a reactive
    response to an unsolicited inquiry → reviewer challenges an off-label
    statement that crosses into promotion, missing fair balance, and over-stated
    claims, with the power to VETO → iterate.

    BOUNDARY (D-LIFESCI-2): distinct from the lifesciences
    PromotionalOffLabelReviewWorkflow — that reviews PROACTIVE promotional
    material where off-label promotion is prohibited; this reviews a REACTIVE
    response to an unsolicited inquiry, where balanced off-label scientific
    exchange is permitted and only PROMOTION of an off-label use is vetoed.

    Convergence gate (D-LIFESCI-4):
        score ≥ threshold (8.0)
        AND zero OFF-LABEL FLAGS
        AND zero BALANCE FLAGS
        AND zero EVIDENCE-LEVEL FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: MedicalInfoRequest,
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
                criteria=_MEDINFO_REVIEW_CRITERIA,
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

        medinfo_checklist = self._build_medinfo_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "off_label_flags": list(dict.fromkeys(accumulated["OFF-LABEL FLAGS:"])),
            "balance_flags": list(dict.fromkeys(accumulated["BALANCE FLAGS:"])),
            "evidence_level_flags": list(
                dict.fromkeys(accumulated["EVIDENCE-LEVEL FLAGS:"])
            ),
            "medinfo_checklist": medinfo_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the approver sees what the AI produced before the REVIEWER VETO
            # banner was prepended.
            # L-HEALTH-1: this field may echo sanitized caller data
            # (inquiry_summary, proposed_response) that can carry patient PHI.
            # Callers must apply downstream PHI handling before logging or sharing.
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
            "OFF-LABEL FLAGS:": (
                "⚠️  OFF-LABEL FLAGS (keep the response reactive and "
                "non-promotional; do not promote an off-label use):"
            ),
            "BALANCE FLAGS:": (
                "⚠️  BALANCE FLAGS (present the corresponding risk/limitation "
                "alongside efficacy):"
            ),
            "EVIDENCE-LEVEL FLAGS:": (
                "⚠️  EVIDENCE-LEVEL FLAGS (state the claim no more strongly than "
                "its evidence supports):"
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
    def _build_medinfo_checklist(
        request: MedicalInfoRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Medical Information / Medical Affairs]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — the drafted response promotes an off-label "
                "use; escalate to Medical Affairs / MLR and do not send until it is "
                "rewritten as a balanced, reactive scientific exchange"
            )
        off_label_flags = accumulated.get("OFF-LABEL FLAGS:", [])
        balance_flags = accumulated.get("BALANCE FLAGS:", [])
        evidence_flags = accumulated.get("EVIDENCE-LEVEL FLAGS:", [])
        if off_label_flags:
            checklist.append(
                f"[ ] ⚠️  OFF-LABEL FLAGS ({len(off_label_flags)}) — keep each "
                "off-label statement reactive and non-promotional"
            )
        if balance_flags:
            checklist.append(
                f"[ ] ⚠️  BALANCE FLAGS ({len(balance_flags)}) — add the "
                "corresponding risk/limitation to each efficacy statement"
            )
        if evidence_flags:
            checklist.append(
                f"[ ] ⚠️  EVIDENCE-LEVEL FLAGS ({len(evidence_flags)}) — recalibrate "
                "each claim to its evidence level"
            )
        checklist.extend([
            "[ ] Confirm the response stays reactive and non-promotional",
            "[ ] Confirm efficacy is presented with fair balance of risk/limitation",
            "[ ] Route any adverse event in the inquiry to pharmacovigilance",
            "[ ] Obtain Medical Information / MLR sign-off before the response is sent",
        ])
        return checklist
