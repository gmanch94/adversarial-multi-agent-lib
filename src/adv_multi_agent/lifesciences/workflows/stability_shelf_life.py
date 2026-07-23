"""
Workflow — Stability / Shelf-Life Justification Review (Lifesciences ·
Pharma/Nutrition)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for shelf-life justification
under ICH Q1A/Q1E. Executor argues a proposed shelf life from the stability
data; reviewer (recommended: different model family) challenges extrapolation
beyond what the data support, ignored degradation trends, and specification
exceedances treated as passing.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Stability-chamber LIMS — timepoint results should be read live from the
       stability LIMS, not caller-pasted text.
    2. ICH Q1E trending engine — trend and poolability analysis should run in
       the controlled stability data-management system, not free text.
    3. Specification database — specification limits should resolve against the
       controlled specification of record.
    4. OOS/OOT investigation system — every out-of-spec / out-of-trend result
       should link to its controlled investigation and disposition.
    5. Qualified approver gate — every AI-suggested conclusion must be reviewed
       and confirmed by a qualified Stability / Analytical Sciences lead; output
       is never a shelf-life determination of record.
    6. Dedicated third-model stability auditor — production should use a
       separately configured auditor model for extrapolation bias detection.
       See ARIS §3.1.
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

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated stability / shelf-life review is "
    "decision-support, not a shelf-life determination and not a regulatory "
    "record. A qualified Stability / Analytical Sciences lead must independently "
    "verify every extrapolation, trend, and specification conclusion against the "
    "controlled stability data before any shelf-life is assigned. Not legal or "
    "medical advice."
)

_STABILITY_REVIEW_CRITERIA = """\
Evaluate this stability / shelf-life review on five dimensions. Score each 0–10.

1. EXTRAPOLATION JUSTIFICATION (30%) — CRITICAL
   Is the proposed shelf life justified by the available long-term (and
   supporting accelerated) data under ICH Q1E, not extrapolated beyond what the
   data and the guidance allow? Penalise extrapolation the data cannot support.
   Flag under EXTRAPOLATION FLAGS:.

2. TREND ANALYSIS (25%) — CRITICAL
   Does the review account for any downward or degradation trend across
   timepoints (assay, impurities, dissolution)? Penalise a trend the proposal
   ignores or dismisses. Flag under TREND FLAGS:.

3. SPECIFICATION CONFORMANCE (20%) — CRITICAL
   Are all results within specification, and is any at/over-specification result
   investigated rather than treated as passing? Penalise an OOS/OOT treated as a
   pass. Flag under SPEC-EXCEEDANCE FLAGS:.

4. STATISTICAL-MODEL FIT (15%)
   Is the statistical approach (regression, poolability of batches per ICH Q1E)
   appropriate for the data? Penalise pooling or modeling that the data do not
   justify.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which attribute, which timepoint,
   which batch)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero EXTRAPOLATION FLAGS AND zero TREND FLAGS AND zero
SPEC-EXCEEDANCE FLAGS: ready for Stability / Analytical Sciences sign-off.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  EXTRAPOLATION FLAGS: [bullet list, or "None detected"]
  TREND FLAGS: [bullet list, or "None detected"]
  SPEC-EXCEEDANCE FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are reviewing a stability / shelf-life justification for a Stability /
Analytical Sciences lead to review. You have no stake in the outcome. Judge the
proposed shelf life against the supplied stability data under ICH Q1A/Q1E — not
against general product norms.

BASE EVERY FINDING ON THE INPUT DATA. Do not assert a trend, exceedance, or
extrapolation basis that is not present in the stability data below.

STABILITY DATA EXCERPT (caller-supplied — verify against the stability LIMS
before acting):
{request_text}

{wiki_context}

Produce a review with:

## Extrapolation justification
- Whether the proposed shelf life is supported by the data under ICH Q1E

## Trend analysis
- Any downward / degradation trend across timepoints (or its absence)

## Specification conformance
- Whether every result is within specification; name any OOS/OOT and its status

## Statistical-model fit
- Whether the regression / batch-poolability approach fits the data

## Findings and recommendations
- Specific findings (which attribute, timepoint, batch) and the shelf-life impact

## Claims
- Specific factual claims about the stability data that ground the review
"""

_REVISION_PROMPT = """\
Revise the stability / shelf-life review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact attribute, timepoint, or batch from the
supplied stability data; do not assert a trend or extrapolation the data lack.
"""


@dataclass
class StabilityShelfLifeRequest:
    """Structured input for the stability / shelf-life review workflow."""

    product_description: str
    """Generic product category and dosage form."""

    proposed_shelf_life: str
    """The shelf life being proposed and its storage statement."""

    storage_conditions: str
    """Long-term and accelerated storage conditions tested."""

    stability_data_summary: str
    """Timepoints, batches, and attributes measured."""

    specification_limits: str
    """The specification limits for the measured attributes."""

    trend_analysis_summary: str
    """Caller's trend analysis across timepoints."""

    oos_oot_events: str
    """Out-of-spec / out-of-trend history and investigation status."""

    extrapolation_basis: str
    """The ICH Q1E argument for extrapolating beyond real-time data."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Proposed shelf life: {self.proposed_shelf_life[:cap]}",
            f"Storage conditions: {self.storage_conditions[:cap]}",
            f"Stability data summary: {self.stability_data_summary[:cap]}",
            f"Specification limits: {self.specification_limits[:cap]}",
            f"Trend analysis summary: {self.trend_analysis_summary[:cap]}",
            f"OOS/OOT events: {self.oos_oot_events[:cap]}",
            f"Extrapolation basis: {self.extrapolation_basis[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "EXTRAPOLATION FLAGS:",
    "TREND FLAGS:",
    "SPEC-EXCEEDANCE FLAGS:",
)


class StabilityShelfLifeWorkflow(BaseWorkflow):
    """
    Adversarial stability / shelf-life review: executor argues a proposed shelf
    life → reviewer challenges over-extrapolation, ignored trends, and
    specification exceedances treated as passing → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero EXTRAPOLATION FLAGS
        AND zero TREND FLAGS
        AND zero SPEC-EXCEEDANCE FLAGS

    No reviewer veto — shelf-life findings drive revision, not an irreversible halt.
    """

    async def run(  # type: ignore[override]
        self,
        request: StabilityShelfLifeRequest,
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
                criteria=_STABILITY_REVIEW_CRITERIA,
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

        stability_checklist = self._build_stability_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "product_description": sanitize_for_prompt(
                    request.product_description, max_chars=200
                ),
                "extrapolation_flags": list(
                    dict.fromkeys(accumulated["EXTRAPOLATION FLAGS:"])
                ),
                "trend_flags": list(dict.fromkeys(accumulated["TREND FLAGS:"])),
                "spec_exceedance_flags": list(
                    dict.fromkeys(accumulated["SPEC-EXCEEDANCE FLAGS:"])
                ),
                "stability_checklist": stability_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "EXTRAPOLATION FLAGS:": (
                "⚠️  EXTRAPOLATION FLAGS (name the shelf-life claim and the ICH Q1E "
                "limit it exceeds; do not assert data the input lacks):"
            ),
            "TREND FLAGS:": (
                "⚠️  TREND FLAGS (name the attribute and the degradation trend across "
                "timepoints the proposal must address):"
            ),
            "SPEC-EXCEEDANCE FLAGS:": (
                "⚠️  SPEC-EXCEEDANCE FLAGS (name the result at/over specification and "
                "require its investigation rather than a pass):"
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
    def _build_stability_checklist(
        request: StabilityShelfLifeRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Stability / Analytical Sciences Lead]")
        if accumulated["EXTRAPOLATION FLAGS:"]:
            checklist.append(
                "[ ] Re-justify or shorten the proposed shelf life for each "
                "flagged over-extrapolation under ICH Q1E"
            )
        if accumulated["TREND FLAGS:"]:
            checklist.append(
                "[ ] Address each flagged degradation trend and its shelf-life "
                "impact for the named attribute"
            )
        if accumulated["SPEC-EXCEEDANCE FLAGS:"]:
            checklist.append(
                "[ ] Link each flagged at/over-specification result to its "
                "OOS/OOT investigation and disposition"
            )
        checklist.append(
            "[ ] Confirm every conclusion resolves against the controlled "
            "stability LIMS data, not the caller summary"
        )
        checklist.append(
            "[ ] Confirm the regression / batch-poolability approach fits the data"
        )
        checklist.append(
            "[ ] Obtain Stability / Analytical Sciences sign-off before a "
            "shelf-life is assigned"
        )
        return checklist
