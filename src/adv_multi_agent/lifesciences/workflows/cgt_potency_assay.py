"""
Workflow — CGT Potency-Assay Lot-Release Adequacy Review (Lifesciences ·
Advanced Therapies / CGT, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to the potency assay
supporting lot release of a cell or gene therapy: executor argues the assay is
mechanism-linked and validated enough to support the lot-release claim; reviewer
(cross-model per ARIS §2.1) challenges a readout not demonstrably linked to the
product's mechanism of action, a release claim the assay cannot support, and
inadequate validation, with the power to VETO when the assay is inadequate to
support release (releasing product without demonstrated clinical activity).

Boundary (D-LIFESCI-2): distinct from AssayPerformanceClaimWorkflow, which reviews
an in-vitro-diagnostic analytical/clinical performance claim. This reviews a
therapeutic mechanism-of-action-linked biological-activity lot-release assay.

Veto gate (D-LIFESCI-8): fires when the potency assay is inadequate to support
lot release — the readout is not linked to clinical activity, or validation is
insufficient for a release-critical method — such that releasing on it risks
releasing product without demonstrated activity.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Bioassay LIMS — potency results should resolve against the controlled
       bioassay LIMS, not caller-pasted summaries.
    2. Assay-qualification / validation records — validation status should
       reconcile against controlled qualification/validation reports.
    3. Mechanism-of-action / pharmacology knowledge base — the MoA linkage should
       be grounded in the controlled pharmacology knowledge base.
    4. Lot-release / QC system — the release claim must map into the controlled
       lot-release system before any disposition.
    5. Qualified approver gate — every AI-suggested release conclusion must be
       confirmed by a qualified CMC / Analytical + QE reviewer. Output is never a
       release of record.
    6. Dedicated third-model potency auditor — production should use a separately
       configured auditor model for release-inflation bias detection. See
       ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated potency-assay adequacy review is "
    "decision-support, not a lot-release of record and not a regulatory "
    "submission. A qualified CMC / Analytical Development + Quality Engineering "
    "reviewer must independently confirm the mechanism-of-action linkage, "
    "validation, and release claim before any lot disposition. Not legal or "
    "medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found the "
    "potency assay inadequate to support lot release (readout not linked to "
    "clinical activity, or validation insufficient); releasing on it risks "
    "releasing product without demonstrated activity. See metadata['veto_reason']. "
    "Escalate to CMC / Analytical Development + Quality Engineering."
)

_FLAG_HEADERS = ("MOA-LINKAGE FLAGS:", "LOT-RELEASE-CLAIM FLAGS:", "ASSAY-VALIDATION FLAGS:")

_POTENCY_REVIEW_CRITERIA = """\
Evaluate this potency-assay adequacy review on five dimensions. Score each 0–10.

1. MECHANISM-OF-ACTION LINKAGE (30%) — CRITICAL
   Is the assay readout demonstrably linked to the product's mechanism of action
   / clinical activity? Penalise a readout that measures a surrogate not tied to
   activity. Flag under MOA-LINKAGE FLAGS:.

2. LOT-RELEASE CLAIM SUPPORT (25%) — CRITICAL
   Does the assay plus its acceptance criteria actually support the stated
   lot-release claim? Penalise a claim beyond what the assay supports. Flag under
   LOT-RELEASE-CLAIM FLAGS:.

3. ASSAY VALIDATION (20%) — CRITICAL
   Is the assay validated for a release-critical method (accuracy, precision,
   specificity, range, stability-indicating capability)? Penalise inadequate
   validation. Flag under ASSAY-VALIDATION FLAGS:.

4. SURROGATE / MATRIX JUSTIFICATION (15%)
   If a surrogate readout or a matrix substitution is used, is it justified?
   Penalise an unjustified surrogate.

5. ACTIONABILITY (10%)
   Is each finding specific enough for CMC to resolve (which readout, which
   criterion, which validation element)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the potency assay is inadequate to support lot release — the
readout is not linked to clinical activity, or validation is insufficient for a
release-critical method — such that releasing on it risks releasing product
without demonstrated activity.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero MOA-LINKAGE FLAGS AND zero LOT-RELEASE-CLAIM FLAGS AND zero
ASSAY-VALIDATION FLAGS AND no VETO: ready for CMC + QE sign-off. Otherwise:
requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  MOA-LINKAGE FLAGS: [bullet list, or "None detected"]
  LOT-RELEASE-CLAIM FLAGS: [bullet list, or "None detected"]
  ASSAY-VALIDATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are reviewing the potency assay supporting lot release of a cell or gene
therapy for a qualified CMC / Analytical Development + Quality Engineering
reviewer. You have no stake in the outcome. Assess whether the assay is
mechanism-linked and validated enough to support the stated lot-release claim,
grounded only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

POTENCY-ASSAY DATA:
{request_text}

{wiki_context}

Produce a structured review with exactly these sections:

## Mechanism-of-action linkage
State whether the assay readout is linked to the product's mechanism of action /
clinical activity; identify any surrogate not tied to activity.

## Lot-release claim
State whether the assay plus acceptance criteria support the stated release claim;
identify any claim beyond what the assay supports.

## Assay validation
State whether the assay is validated for a release-critical method (accuracy,
precision, specificity, range, stability-indicating).

## Surrogate / matrix justification
State whether any surrogate readout or matrix substitution is justified.

## Release-adequacy conclusion
State whether the potency assay is adequate to support lot release, or whether it
is inadequate.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this potency-assay adequacy review. Address EVERY issue in the reviewer's
critique, especially any MOA-LINKAGE FLAGS, LOT-RELEASE-CLAIM FLAGS, or
ASSAY-VALIDATION FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any MOA-LINKAGE flag: link the readout to the mechanism of action, or
acknowledge the assay does not measure clinical activity.
⚠️  For any LOT-RELEASE-CLAIM flag: narrow the release claim to what the assay
and criteria support.
⚠️  For any ASSAY-VALIDATION flag: cite the validation element that resolves the
gap, or acknowledge the method is not validated for release.
"""


@dataclass
class PotencyAssayRequest:
    """Structured input for the CGT potency-assay lot-release adequacy review."""

    product_description: str
    """Generic product category (e.g. an autologous CAR-T, an AAV gene therapy)."""

    mechanism_of_action: str
    """The product's mechanism of action / intended clinical activity."""

    potency_assay_description: str
    """The potency assay: matrix, readout, and format."""

    moa_linkage_rationale: str
    """Rationale linking the assay readout to the mechanism of action."""

    assay_validation_summary: str
    """Validation summary: accuracy, precision, specificity, range, stability-indicating."""

    acceptance_criteria: str
    """Lot-release acceptance criteria for the potency assay."""

    lot_release_claim: str
    """The stated lot-release claim the assay is used to support."""

    surrogate_or_matrix_justification: str
    """Justification for any surrogate readout or matrix substitution."""

    stability_indicating_evidence: str
    """Evidence the assay is stability-indicating over shelf life."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Mechanism of action: {self.mechanism_of_action[:cap]}",
            f"Potency assay description: {self.potency_assay_description[:cap]}",
            f"MoA linkage rationale: {self.moa_linkage_rationale[:cap]}",
            f"Assay validation summary: {self.assay_validation_summary[:cap]}",
            f"Acceptance criteria: {self.acceptance_criteria[:cap]}",
            f"Lot-release claim: {self.lot_release_claim[:cap]}",
            f"Surrogate / matrix justification: {self.surrogate_or_matrix_justification[:cap]}",
            f"Stability-indicating evidence: {self.stability_indicating_evidence[:cap]}",
        ])


class CGTPotencyAssayWorkflow(BaseWorkflow):
    """
    Adversarial CGT potency-assay lot-release adequacy review: executor argues the
    assay is mechanism-linked and validated → reviewer challenges a readout not
    linked to activity, an unsupported release claim, and inadequate validation,
    with the power to VETO → iterate.

    Convergence gate (D-LIFESCI-8):
        score ≥ threshold (8.0)
        AND zero MOA-LINKAGE FLAGS
        AND zero LOT-RELEASE-CLAIM FLAGS
        AND zero ASSAY-VALIDATION FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the wiki.
    The verbatim veto directive is recorded in metadata['veto_reason'];
    metadata['first_draft'] captures the clean executor draft from the vetoed round.
    """

    async def run(  # type: ignore[override]
        self,
        request: PotencyAssayRequest,
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
                criteria=_POTENCY_REVIEW_CRITERIA,
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

        potency_checklist = self._build_potency_checklist(request, accumulated, veto_reason)

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "moa_linkage_flags": list(dict.fromkeys(accumulated["MOA-LINKAGE FLAGS:"])),
            "lot_release_claim_flags": list(
                dict.fromkeys(accumulated["LOT-RELEASE-CLAIM FLAGS:"])
            ),
            "assay_validation_flags": list(
                dict.fromkeys(accumulated["ASSAY-VALIDATION FLAGS:"])
            ),
            "potency_checklist": potency_checklist,
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
            "MOA-LINKAGE FLAGS:": (
                "⚠️  MOA-LINKAGE FLAGS (link the readout to the mechanism of action, "
                "or acknowledge the assay does not measure clinical activity):"
            ),
            "LOT-RELEASE-CLAIM FLAGS:": (
                "⚠️  LOT-RELEASE-CLAIM FLAGS (narrow the release claim to what the "
                "assay and criteria support):"
            ),
            "ASSAY-VALIDATION FLAGS:": (
                "⚠️  ASSAY-VALIDATION FLAGS (cite the validation element that resolves "
                "the gap, or acknowledge the method is not validated for release):"
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
    def _build_potency_checklist(
        request: PotencyAssayRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: CMC / Analytical Development + Quality Engineering]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — do not release on this potency assay; escalate "
                "to CMC / Analytical Development + QE and requalify the assay before "
                "any lot disposition"
            )
        moa_flags = accumulated.get("MOA-LINKAGE FLAGS:", [])
        claim_flags = accumulated.get("LOT-RELEASE-CLAIM FLAGS:", [])
        validation_flags = accumulated.get("ASSAY-VALIDATION FLAGS:", [])
        if moa_flags:
            checklist.append(
                f"[ ] ⚠️  MOA-LINKAGE FLAGS ({len(moa_flags)}) — demonstrate the readout "
                "is linked to the mechanism of action"
            )
        if claim_flags:
            checklist.append(
                f"[ ] ⚠️  LOT-RELEASE-CLAIM FLAGS ({len(claim_flags)}) — narrow the "
                "release claim to what the assay supports"
            )
        if validation_flags:
            checklist.append(
                f"[ ] ⚠️  ASSAY-VALIDATION FLAGS ({len(validation_flags)}) — complete "
                "validation for the release-critical method"
            )
        checklist.extend([
            "[ ] Confirm the assay readout is linked to the mechanism of action",
            "[ ] Confirm the acceptance criteria support the lot-release claim",
            "[ ] Confirm the assay is validated and stability-indicating",
            "[ ] Obtain CMC + QE sign-off before any lot disposition",
        ])
        return checklist
