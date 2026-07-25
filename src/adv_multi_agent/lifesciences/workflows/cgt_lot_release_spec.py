"""
Workflow — CGT Lot-Release Specification Adequacy Audit (Lifesciences ·
Advanced Therapies / CGT)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to the lot-release
specification set of a small-lot, short-shelf-life cell or gene therapy: executor
summarises the proposed release specifications; reviewer (cross-model per ARIS
§2.1) challenges a release-critical attribute lacking an adequate specification,
sampling / test-consumption impractical for the lot size, and a rapid / real-time
release strategy inadequately justified for the short shelf life.

No reviewer veto (D-LIFESCI-8): this is an advisory spec-adequacy audit.

Cross-reference: potency-as-release-attribute *adequacy* (mechanism-of-action
linkage) is CGTPotencyAssayWorkflow's veto call; this workflow audits whole-
spec-set coverage only — it does not duplicate the potency-linkage logic.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. QC LIMS — release results should resolve against the controlled QC LIMS,
       not caller-pasted summaries.
    2. Specification-management system — each release specification and its
       acceptance criterion should reconcile against the controlled spec system.
    3. Stability database — shelf-life and storage claims should read the
       controlled stability database, not a narrative.
    4. Rapid-microbial-method validation records — the short-shelf-life release
       strategy should map to validated rapid / real-time-release methods.
    5. Qualified QC approver gate — every AI-suggested spec conclusion must be
       confirmed by a qualified QC / QE reviewer. Output is never a release of
       record.
    6. Dedicated third-model spec auditor — production should use a separately
       configured auditor model for coverage-gap bias detection. See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import (
    extract_flags,
    sanitize_for_prompt,
    sanitize_request_text,
    truncate_flag_display,
)
from ...core.workflow import BaseWorkflow, WorkflowResult

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated lot-release specification audit is "
    "decision-support, not a release of record and not a regulatory submission. "
    "A qualified QC / Quality Engineering reviewer must independently confirm the "
    "release-specification set, sampling plan, and short-shelf-life release "
    "strategy against the controlled records before any lot disposition. Not "
    "legal or medical advice."
)

_LOT_RELEASE_REVIEW_CRITERIA = """\
Evaluate this lot-release specification audit on five dimensions. Score each 0–10.

1. RELEASE-ATTRIBUTE COVERAGE (30%) — CRITICAL
   Does every release-critical attribute (identity, purity, potency, sterility,
   safety, viability) have an adequate specification with an acceptance criterion?
   Penalise a missing or inadequate specification. Flag under SPEC-COVERAGE FLAGS.

2. SMALL-LOT SAMPLING (25%) — CRITICAL
   Is the sampling / test-consumption plan practical for the lot size, and do the
   acceptance criteria account for small-lot statistics? Penalise a plan that
   consumes the lot or ignores small-n. Flag under SMALL-LOT FLAGS.

3. SHORT-SHELF-LIFE RELEASE (20%) — CRITICAL
   Is the rapid / real-time-release strategy for the short shelf life adequately
   justified (e.g. sterility / mycoplasma released before final results)? Penalise
   an unjustified release-before-result. Flag under SHELF-LIFE FLAGS.

4. STABILITY & OUT-OF-SPECIFICATION HANDLING (15%)
   Do the stability program and out-of-specification handling support the claimed
   shelf life and disposition path? Penalise unsupported claims.

5. ACTIONABILITY (10%)
   Is each gap specific enough for QC to close (which attribute, which criterion,
   which method)? Penalise vague findings.

Overall score = weighted average.
Score >= 7.5 AND zero SPEC-COVERAGE FLAGS AND zero SMALL-LOT FLAGS AND zero
SHELF-LIFE FLAGS, then ready for QC sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SPEC-COVERAGE FLAGS: [bullet list, or "None detected"]
  SMALL-LOT FLAGS: [bullet list, or "None detected"]
  SHELF-LIFE FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are auditing the lot-release specification set of a small-lot, short-shelf-life
cell or gene therapy for a QC / Quality Engineering reviewer. You have no stake in
the outcome. Assess release-attribute coverage, small-lot sampling, and the
short-shelf-life release strategy against the supplied data — not against general
norms.

BASE EVERY FINDING ON THE INPUT DATA ONLY. Do not assert a specification or
sampling plan not present in the input.

LOT-RELEASE DATA (caller-supplied — verify against the QC LIMS before acting):
{request_text}

{wiki_context}

Produce an audit with:

## Release-attribute coverage
For each release-critical attribute (identity, purity, potency, sterility, safety,
viability), state whether an adequate specification with acceptance criterion is
present; name any gap.

## Small-lot sampling
Assess whether the sampling / test-consumption plan is practical for the lot size
and whether acceptance criteria account for small-lot statistics.

## Short-shelf-life release
Assess whether the rapid / real-time-release strategy is justified for the short
shelf life; name any release-before-result risk.

## Stability and out-of-specification handling
Assess whether stability and OOS handling support the claimed shelf life.

## Gaps and recommendations
Specific, closeable gaps (which attribute, which criterion, which method).

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this lot-release specification audit based on reviewer critique. Address
EVERY issue, especially any SPEC-COVERAGE FLAGS, SMALL-LOT FLAGS, or SHELF-LIFE
FLAGS.

ORIGINAL AUDIT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact missing specification, sampling detail,
or release-strategy justification from the input; do not assert coverage not
present in the supplied data.
"""


@dataclass
class LotReleaseSpecRequest:
    """Structured input for the CGT lot-release specification adequacy audit."""

    product_description: str
    """Generic product category and format (e.g. an autologous cell therapy, single-dose)."""

    proposed_release_specifications: str
    """Proposed release specifications (identity, purity, potency, sterility, safety, viability) with criteria."""

    lot_size_and_format: str
    """Lot size and format (autologous single-dose / allogeneic bank)."""

    shelf_life_and_storage: str
    """Shelf life and storage conditions."""

    rapid_or_real_time_methods: str
    """Rapid / real-time-release methods and their justification for the short shelf life."""

    sterility_and_mycoplasma_strategy: str
    """Sterility and mycoplasma testing / release strategy."""

    out_of_specification_handling: str
    """Out-of-specification handling and disposition path."""

    stability_program_summary: str
    """Stability program supporting the claimed shelf life."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Proposed release specifications: {self.proposed_release_specifications[:cap]}",
            f"Lot size and format: {self.lot_size_and_format[:cap]}",
            f"Shelf life and storage: {self.shelf_life_and_storage[:cap]}",
            f"Rapid / real-time methods: {self.rapid_or_real_time_methods[:cap]}",
            f"Sterility and mycoplasma strategy: {self.sterility_and_mycoplasma_strategy[:cap]}",
            f"Out-of-specification handling: {self.out_of_specification_handling[:cap]}",
            f"Stability program summary: {self.stability_program_summary[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "SPEC-COVERAGE FLAGS:",
    "SMALL-LOT FLAGS:",
    "SHELF-LIFE FLAGS:",
)


class CGTLotReleaseSpecWorkflow(BaseWorkflow):
    """
    Adversarial CGT lot-release specification adequacy audit: executor summarises
    the release specifications → reviewer challenges an uncovered release-critical
    attribute, an impractical small-lot sampling plan, and an unjustified
    short-shelf-life release strategy → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero SPEC-COVERAGE FLAGS
        AND zero SMALL-LOT FLAGS
        AND zero SHELF-LIFE FLAGS

    No reviewer veto — spec-adequacy corrections are reversible. Potency-linkage
    adequacy is CGTPotencyAssayWorkflow's veto call, not duplicated here.
    """

    async def run(  # type: ignore[override]
        self,
        request: LotReleaseSpecRequest,
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
                criteria=_LOT_RELEASE_REVIEW_CRITERIA,
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

        lot_release_checklist = self._build_lot_release_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "product_description": sanitize_for_prompt(
                    request.product_description, max_chars=200
                ),
                "spec_coverage_flags": list(dict.fromkeys(accumulated["SPEC-COVERAGE FLAGS:"])),
                "small_lot_flags": list(dict.fromkeys(accumulated["SMALL-LOT FLAGS:"])),
                "shelf_life_flags": list(dict.fromkeys(accumulated["SHELF-LIFE FLAGS:"])),
                "lot_release_checklist": lot_release_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "SPEC-COVERAGE FLAGS:": (
                "⚠️  SPEC-COVERAGE FLAGS (name the release-critical attribute lacking "
                "an adequate specification and acceptance criterion):"
            ),
            "SMALL-LOT FLAGS:": (
                "⚠️  SMALL-LOT FLAGS (cite the impractical sampling / test-consumption "
                "or the small-lot statistic ignored):"
            ),
            "SHELF-LIFE FLAGS:": (
                "⚠️  SHELF-LIFE FLAGS (cite the unjustified rapid / real-time release "
                "for the short shelf life):"
            ),
        }
        parts: list[str] = []
        for header in _FLAG_HEADERS:
            items = current[header]
            if not items:
                continue
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(items)
            )
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _build_lot_release_checklist(
        request: LotReleaseSpecRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Quality Control / Quality Engineering]"]
        if accumulated["SPEC-COVERAGE FLAGS:"]:
            checklist.append(
                "[ ] Add an adequate specification + acceptance criterion for each "
                "flagged release-critical attribute"
            )
        if accumulated["SMALL-LOT FLAGS:"]:
            checklist.append(
                "[ ] Revise the sampling / test-consumption plan for each flagged "
                "small-lot impracticality"
            )
        if accumulated["SHELF-LIFE FLAGS:"]:
            checklist.append(
                "[ ] Justify or revise each flagged rapid / real-time-release "
                "decision for the short shelf life"
            )
        checklist.extend([
            "[ ] Confirm every release-critical attribute has a validated method + criterion",
            "[ ] Confirm the sampling plan is practical for the lot size",
            "[ ] Confirm the short-shelf-life release strategy is validated and justified",
            "[ ] Obtain QC / Quality Engineering sign-off before lot disposition",
        ])
        return checklist
