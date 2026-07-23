"""
Workflow — UDI Labeling Consistency Review (Lifesciences · Devices)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for Unique Device
Identification labeling (US FDA UDI / GUDID, EU UDI / EUDAMED). Executor reviews
UDI construction and label/database consistency; reviewer (recommended:
different model family) challenges invalid identifiers, database-to-label
inconsistencies, and packaging tiers missing their UDI.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Labeling-management system — label content should be read live from the
       controlled labeling-management system, not caller-pasted text.
    2. GUDID / EUDAMED gateway — database attributes should reconcile against
       the submitted GUDID / EUDAMED record, and this workflow does not submit.
    3. Artwork-management system — human-readable and AIDC content should
       resolve against the controlled artwork of record.
    4. Issuing-agency registry — DI/PI structure should validate against the
       issuing agency's rules (GS1 / HIBCC / ICCBBA).
    5. Qualified approver gate — every AI-suggested finding must be reviewed and
       confirmed by a qualified Regulatory Labeling / UDI coordinator; output is
       never an auto-submitted UDI record.
    6. Dedicated third-model labeling auditor — production should use a
       separately configured auditor model for identifier bias detection. See
       ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated UDI labeling review is decision-support, "
    "not a labeling release and not a submitted UDI record. A qualified "
    "Regulatory Labeling / UDI coordinator must independently verify every "
    "identifier, database attribute, and packaging tier against the controlled "
    "labeling and GUDID / EUDAMED systems before release. Not legal or medical advice."
)

_UDI_REVIEW_CRITERIA = """\
Evaluate this UDI labeling review on five dimensions. Score each 0–10.

1. IDENTIFIER STRUCTURE (30%) — CRITICAL
   Is the DI/PI structure valid for the declared issuing agency (GS1 / HIBCC /
   ICCBBA), with the required production identifiers present? Penalise an invalid
   or incomplete identifier structure. Flag under IDENTIFIER FLAGS:.

2. GUDID/EUDAMED CONSISTENCY (25%) — CRITICAL
   Does every database attribute (GUDID / EUDAMED) match the label and artwork?
   Penalise a database attribute inconsistent with the label. Flag under
   GUDID-CONSISTENCY FLAGS:.

3. PACKAGING-TIER COVERAGE (20%) — CRITICAL
   Does every packaging tier that requires a UDI carry one, with the hierarchy DI
   relationships intact? Penalise a packaging tier missing its UDI or a broken
   hierarchy. Flag under PACKAGING-TIER FLAGS:.

4. LABEL-ARTWORK CONSISTENCY (15%)
   Are the human-readable and AIDC (barcode) forms consistent, and are
   direct-mark rules for reusable devices satisfied? Penalise HRI/AIDC mismatch.

5. ACTIONABILITY (10%)
   Is each finding specific enough to correct (which identifier, which attribute,
   which tier)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero IDENTIFIER FLAGS AND zero GUDID-CONSISTENCY FLAGS AND zero
PACKAGING-TIER FLAGS: ready for Regulatory Labeling sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  IDENTIFIER FLAGS: [bullet list, or "None detected"]
  GUDID-CONSISTENCY FLAGS: [bullet list, or "None detected"]
  PACKAGING-TIER FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are reviewing UDI labeling for a Regulatory Labeling / UDI coordinator to
review. You have no stake in the outcome. Judge the UDI construction and the
label-to-database consistency against the supplied evidence — not against
general labeling norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert an identifier, database
attribute, or packaging tier that is not present in the material below.

UDI LABELING EXCERPT (caller-supplied — verify against the controlled labeling
and GUDID / EUDAMED systems before acting):
{request_text}

{wiki_context}

Produce a review with:

## Identifier structure
- Whether the DI/PI structure is valid for the issuing agency

## Database consistency
- Whether GUDID / EUDAMED attributes match the label and artwork

## Packaging-tier coverage
- Whether every tier requiring a UDI carries one; name any gap

## Label-artwork consistency
- Whether human-readable and AIDC forms agree; direct-mark rules

## Findings and recommendations
- Specific findings (which identifier, attribute, tier) and the labeling impact

## Claims
- Specific factual claims about the supplied evidence that ground the review
"""

_REVISION_PROMPT = """\
Revise the UDI labeling review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact identifier, database attribute, or
packaging tier from the supplied evidence; do not assert a value the evidence
does not show.
"""


@dataclass
class UDILabelingRequest:
    """Structured input for the UDI labeling review workflow."""

    device_identifier: str
    """Generic device category and model."""

    di_pi_structure: str
    """Device Identifier and Production Identifier composition."""

    issuing_agency: str
    """Issuing agency (GS1 / HIBCC / ICCBBA)."""

    gudid_record_summary: str
    """Attributes submitted to GUDID / EUDAMED."""

    label_artwork_summary: str
    """Human-readable and AIDC content on each label tier."""

    packaging_hierarchy: str
    """Each / inner / case packaging tiers and their UDIs."""

    direct_marking_status: str
    """Direct-mark status for reusable devices."""

    regional_scope: str
    """Regions where the device is marketed (US / EU / other)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Device identifier: {self.device_identifier[:cap]}",
            f"DI/PI structure: {self.di_pi_structure[:cap]}",
            f"Issuing agency: {self.issuing_agency[:cap]}",
            f"GUDID record summary: {self.gudid_record_summary[:cap]}",
            f"Label artwork summary: {self.label_artwork_summary[:cap]}",
            f"Packaging hierarchy: {self.packaging_hierarchy[:cap]}",
            f"Direct marking status: {self.direct_marking_status[:cap]}",
            f"Regional scope: {self.regional_scope[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "IDENTIFIER FLAGS:",
    "GUDID-CONSISTENCY FLAGS:",
    "PACKAGING-TIER FLAGS:",
)


class UDILabelingWorkflow(BaseWorkflow):
    """
    Adversarial UDI labeling review: executor reviews UDI construction +
    consistency → reviewer challenges invalid identifiers, database-to-label
    inconsistencies, and packaging tiers missing their UDI → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero IDENTIFIER FLAGS
        AND zero GUDID-CONSISTENCY FLAGS
        AND zero PACKAGING-TIER FLAGS

    No reviewer veto — labeling corrections are reversible before release.
    """

    async def run(  # type: ignore[override]
        self,
        request: UDILabelingRequest,
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
                criteria=_UDI_REVIEW_CRITERIA,
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

        udi_checklist = self._build_udi_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "device_identifier": sanitize_for_prompt(
                    request.device_identifier, max_chars=200
                ),
                "identifier_flags": list(dict.fromkeys(accumulated["IDENTIFIER FLAGS:"])),
                "gudid_consistency_flags": list(
                    dict.fromkeys(accumulated["GUDID-CONSISTENCY FLAGS:"])
                ),
                "packaging_tier_flags": list(
                    dict.fromkeys(accumulated["PACKAGING-TIER FLAGS:"])
                ),
                "udi_checklist": udi_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "IDENTIFIER FLAGS:": (
                "⚠️  IDENTIFIER FLAGS (name the invalid or incomplete DI/PI element "
                "against the issuing-agency rules):"
            ),
            "GUDID-CONSISTENCY FLAGS:": (
                "⚠️  GUDID-CONSISTENCY FLAGS (name the database attribute that does "
                "not match the label / artwork):"
            ),
            "PACKAGING-TIER FLAGS:": (
                "⚠️  PACKAGING-TIER FLAGS (name the packaging tier missing its UDI or "
                "the broken hierarchy relationship):"
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
    def _build_udi_checklist(
        request: UDILabelingRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Regulatory Labeling / UDI Coordinator]")
        if accumulated["IDENTIFIER FLAGS:"]:
            checklist.append(
                "[ ] Correct each flagged DI/PI element against the issuing-agency "
                "rules before release"
            )
        if accumulated["GUDID-CONSISTENCY FLAGS:"]:
            checklist.append(
                "[ ] Reconcile each flagged GUDID / EUDAMED attribute with the "
                "label and artwork of record"
            )
        if accumulated["PACKAGING-TIER FLAGS:"]:
            checklist.append(
                "[ ] Apply the missing UDI to each flagged packaging tier and "
                "repair the hierarchy relationship"
            )
        checklist.append(
            "[ ] Confirm every attribute resolves against the controlled "
            "labeling and GUDID / EUDAMED systems, not the caller summary"
        )
        checklist.append(
            "[ ] Confirm human-readable and AIDC forms agree and direct-mark "
            "rules are satisfied"
        )
        checklist.append(
            "[ ] Obtain Regulatory Labeling sign-off before the labeling is "
            "released or the UDI record is submitted"
        )
        return checklist
