"""
Workflow — Promotional Off-Label / Fair-Balance Review (Lifesciences ·
Pharma/Device MLR, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to promotional-material
medical/legal/regulatory (MLR) review: executor reviews each promotional claim
against the approved labeling for on-label consistency, fair balance, and
substantiation; reviewer (cross-model per ARIS §2.1) challenges any claim outside
the approved indication, absent or de-emphasised risk information, and
unsupported efficacy/comparative claims, with the power to VETO when the material
would likely draw an FDA enforcement or untitled letter (clear off-label
promotion or omission of material risk).

Veto gate (D-LIFESCI-3): fires when the material would likely draw an FDA
enforcement/untitled letter — clear off-label promotion, or omission of material
risk information — such that releasing it would misbrand the product.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Promotional-review DAM — materials and their review state should resolve
       against the controlled promotional-review digital-asset-management
       system, not caller-pasted material text.
    2. Approved-labeling repository — the approved indication, warnings, and
       contraindications should reconcile against the controlled approved-labeling
       repository, not caller-supplied text.
    3. Claims / reference library — every claim and its cited references should
       reconcile against the controlled claims/reference library before release.
    4. FDA Form 2253 submission — released material must be logged to the FDA
       Form 2253 process; this workflow does not file it.
    5. Dedicated third-model fair-balance auditor — production should use a
       separately configured auditor model for benefit-risk-prominence bias
       detection. See ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated promotional-material review is "
    "decision-support, not MLR approval and not a regulatory clearance. A "
    "qualified MLR committee (Medical, Legal, Regulatory) must independently "
    "confirm on-label consistency, fair balance, and substantiation before any "
    "material is released. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found the "
    "material would likely draw an FDA enforcement/untitled letter (clear "
    "off-label promotion or omission of material risk). See "
    "metadata['veto_reason']. Escalate to MLR; do not release the material."
)

_FLAG_HEADERS = ("OFF-LABEL FLAGS:", "FAIR-BALANCE FLAGS:", "SUBSTANTIATION FLAGS:")

_PROMO_REVIEW_CRITERIA = """\
Evaluate this promotional-material review on five dimensions. Score each 0–10.

1. ON-LABEL CONSISTENCY (30%) — CRITICAL
   Is every claim within the approved indication, population, and dosing?
   Penalise any claim outside the approved label. Flag under OFF-LABEL FLAGS:.

2. FAIR BALANCE (25%) — CRITICAL
   Is risk / limitation information present and comparably prominent to the
   benefit claims? Penalise absent or de-emphasised risk information. Flag under
   FAIR-BALANCE FLAGS:.

3. CLAIM SUBSTANTIATION (20%) — CRITICAL
   Is each efficacy / comparative / superiority claim backed by substantial
   evidence or an adequate head-to-head citation? Penalise unsupported or
   inadequately cited claims. Flag under SUBSTANTIATION FLAGS:.

4. REFERENCE ADEQUACY (15%)
   Do the cited references actually support the claims they are attached to?
   Penalise references that do not support the claim.

5. ACTIONABILITY (10%)
   Is each finding specific enough for the MLR reviewer to resolve (which claim,
   which risk, which reference)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the material would likely draw an FDA enforcement or untitled
letter — clear off-label promotion, or omission of material risk information.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero OFF-LABEL FLAGS AND zero FAIR-BALANCE FLAGS AND zero
SUBSTANTIATION FLAGS AND no VETO: ready for MLR sign-off. Otherwise: requires
revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  OFF-LABEL FLAGS: [bullet list, or "None detected"]
  FAIR-BALANCE FLAGS: [bullet list, or "None detected"]
  SUBSTANTIATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are reviewing a piece of promotional material for a medical product for a
qualified MLR committee (Medical, Legal, Regulatory). You have no stake in the
outcome. Your job is to review each promotional claim against the approved
labeling for on-label consistency, fair balance, and substantiation, grounded
only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

PROMOTIONAL-MATERIAL DATA:
{request_text}

{wiki_context}

Produce a structured promotional-material review with exactly these sections:

## Claim-by-claim label check
Map each promotional claim to the approved labeling. State whether each claim is
within the approved indication, population, and dosing. Identify any claim that
promotes an off-label use.

## Fair-balance assessment
State whether risk / limitation information is present and comparably prominent
to the benefit claims. Identify any absent or de-emphasised risk information.

## Substantiation and references
For each efficacy / comparative / superiority claim, state whether it is backed
by substantial evidence or an adequate citation. Identify any unsupported claim.

## Comparative-claim check
For each comparative or superiority claim, state whether an adequate head-to-head
citation supports it. Identify any comparative claim without adequate support.

## Redline recommendations
State the specific change required for each finding (remove the claim, restrict
it to the approved indication, add risk information, or attach a citation).

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this promotional-material review. Address EVERY issue in the reviewer's
critique, especially any OFF-LABEL FLAGS, FAIR-BALANCE FLAGS, or SUBSTANTIATION
FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any OFF-LABEL flag: remove the claim or restrict it to the approved
indication.
⚠️  For any FAIR-BALANCE flag: add risk information with comparable prominence.
⚠️  For any SUBSTANTIATION flag: attach an adequate citation or remove the claim.
"""


@dataclass
class PromoReviewRequest:
    """Structured input for the promotional off-label / fair-balance review workflow."""

    material_type: str
    """Generic category and format of the promotional material (e.g. an HCP visual aid)."""

    target_audience: str
    """Intended audience: healthcare professionals, consumers (DTC), payers."""

    promo_claims: str
    """The promotional claims made in the material, one per statement."""

    approved_labeling_reference: str
    """Approved labeling: indication, population, warnings, contraindications."""

    cited_references: str
    """References cited in support of the claims."""

    risk_information_present: str
    """Risk / safety / limitation information present in the material and its prominence."""

    comparative_claims: str
    """Comparative or superiority claims made and their stated support."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Material type: {self.material_type[:cap]}",
            f"Target audience: {self.target_audience[:cap]}",
            f"Promotional claims: {self.promo_claims[:cap]}",
            f"Approved labeling reference: {self.approved_labeling_reference[:cap]}",
            f"Cited references: {self.cited_references[:cap]}",
            f"Risk information present: {self.risk_information_present[:cap]}",
            f"Comparative claims: {self.comparative_claims[:cap]}",
        ])


class PromotionalOffLabelReviewWorkflow(BaseWorkflow):
    """
    Adversarial promotional-material MLR review: executor reviews each claim
    against the approved labeling → reviewer challenges off-label claims, absent
    or de-emphasised risk information, and unsupported efficacy/comparative
    claims, with the power to VETO → iterate.

    Convergence gate (D-LIFESCI-3):
        score ≥ threshold (8.0)
        AND zero OFF-LABEL FLAGS
        AND zero FAIR-BALANCE FLAGS
        AND zero SUBSTANTIATION FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: PromoReviewRequest,
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
                criteria=_PROMO_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            # Audit-trail writes happen BEFORE the veto check — preserves the
            # round-N draft in wiki + ledger even if vetoed (D-LIFESCI-3).
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

        promo_checklist = self._build_promo_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "material_type": sanitize_for_prompt(
                request.material_type, max_chars=200
            ),
            "off_label_flags": list(dict.fromkeys(accumulated["OFF-LABEL FLAGS:"])),
            "fair_balance_flags": list(
                dict.fromkeys(accumulated["FAIR-BALANCE FLAGS:"])
            ),
            "substantiation_flags": list(
                dict.fromkeys(accumulated["SUBSTANTIATION FLAGS:"])
            ),
            "promo_checklist": promo_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the MLR committee sees what the AI produced before the REVIEWER
            # VETO banner was prepended.
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
                "⚠️  OFF-LABEL FLAGS (remove the claim or restrict it to the "
                "approved indication):"
            ),
            "FAIR-BALANCE FLAGS:": (
                "⚠️  FAIR-BALANCE FLAGS (add risk information with comparable "
                "prominence to the benefit claims):"
            ),
            "SUBSTANTIATION FLAGS:": (
                "⚠️  SUBSTANTIATION FLAGS (attach an adequate citation or remove "
                "the claim):"
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
    def _build_promo_checklist(
        request: PromoReviewRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: MLR Committee (Medical + Legal + Regulatory)]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — do not release the material; escalate to "
                "MLR (likely FDA enforcement/untitled-letter exposure) before any "
                "distribution"
            )
        off_label_flags = accumulated.get("OFF-LABEL FLAGS:", [])
        fair_balance_flags = accumulated.get("FAIR-BALANCE FLAGS:", [])
        substantiation_flags = accumulated.get("SUBSTANTIATION FLAGS:", [])
        if off_label_flags:
            checklist.append(
                f"[ ] ⚠️  OFF-LABEL FLAGS ({len(off_label_flags)}) — "
                "remove or restrict each claim to the approved indication"
            )
        if fair_balance_flags:
            checklist.append(
                f"[ ] ⚠️  FAIR-BALANCE FLAGS ({len(fair_balance_flags)}) — "
                "add risk information with comparable prominence to the benefit claims"
            )
        if substantiation_flags:
            checklist.append(
                f"[ ] ⚠️  SUBSTANTIATION FLAGS ({len(substantiation_flags)}) — "
                "attach adequate substantiation for each claim or remove it"
            )
        checklist.extend([
            "[ ] Remove or restrict every off-label claim to the approved indication",
            "[ ] Add risk information with comparable prominence to the benefit claims",
            "[ ] Attach adequate substantiation for each efficacy / comparative claim",
            "[ ] Obtain MLR sign-off before the material is released",
        ])
        return checklist
