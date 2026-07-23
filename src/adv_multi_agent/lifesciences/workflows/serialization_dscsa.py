"""
Workflow — Serialization / DSCSA Traceability Review (Lifesciences · Pharma)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for pharmaceutical
serialization and Drug Supply Chain Security Act (DSCSA) traceability. Executor
reviews the serialization scheme, aggregation, and EPCIS/verification coverage;
reviewer (recommended: different model family) challenges a broken aggregation
link, a missing traceability event, and a saleable return processed without
product-identifier verification.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Serialization / L4 system — the serialization scheme and serial numbers
       should resolve against the controlled serialization system, not
       caller-pasted text.
    2. EPCIS repository + trading-partner exchange gateway — the commissioning,
       packing, and shipping events should resolve against the controlled EPCIS
       repository and partner-exchange gateway.
    3. Verification-router service — product-identifier verification for suspect
       and returned product should resolve against the controlled verification
       service.
    4. Packaging-line aggregation capture — the parent-child aggregation should
       resolve against the controlled line-capture system.
    5. Qualified approver gate — every AI-suggested traceability conclusion must
       be reviewed by a qualified Serialization / Supply-Chain Compliance lead.
       Output is never an auto-certified DSCSA compliance record.
    6. Dedicated third-model traceability auditor — production should use a
       separately configured auditor model for aggregation bias detection.
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
    "ADVISORY ONLY — This AI-generated serialization / DSCSA traceability review "
    "is decision-support, not a DSCSA compliance record and not a regulatory "
    "submission. A qualified Serialization / Supply-Chain Compliance lead must "
    "independently confirm the aggregation, traceability events, and saleable-"
    "return verification before any traceability conclusion is filed. Not legal "
    "or medical advice."
)

_SERIALIZATION_REVIEW_CRITERIA = """\
Evaluate this serialization / DSCSA traceability review on five dimensions. Score each 0–10.

1. AGGREGATION INTEGRITY (30%) — CRITICAL
   Is every parent-child aggregation link across packaging tiers (item / case /
   pallet) present and correct? Penalise a broken or missing aggregation link.
   Flag under AGGREGATION FLAGS:.

2. EVENT / TRACEABILITY COVERAGE (25%) — CRITICAL
   Is every required EPCIS event and trading-partner data element present, so
   unit-level traceability is unbroken? Penalise a missing event or data element.
   Flag under TRACEABILITY FLAGS:.

3. SALEABLE-RETURN VERIFICATION (20%) — CRITICAL
   Is every saleable return verified at the product-identifier (unit) level before
   resale? Penalise a saleable return processed without the required verification.
   Flag under SALEABLE-RETURN FLAGS:.

4. INTEROPERABILITY READINESS (15%)
   Is the system ready for enhanced unit-level traceability and interoperable
   exchange? Penalise gaps in interoperability capability.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which tier, which event, which
   return)? Penalise vague findings.

Overall score = weighted average.
Score >= 7.5 AND zero AGGREGATION FLAGS AND zero TRACEABILITY FLAGS AND zero
SALEABLE-RETURN FLAGS: ready for Supply-Chain Compliance sign-off. Otherwise:
requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  AGGREGATION FLAGS: [bullet list, or "None detected"]
  TRACEABILITY FLAGS: [bullet list, or "None detected"]
  SALEABLE-RETURN FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are reviewing a serialization / DSCSA traceability configuration for a
Supply-Chain Compliance lead to approve. You have no stake in the outcome. Assess
the aggregation integrity, the EPCIS/traceability event coverage, and the
saleable-return verification — grounded only in the data supplied.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert an aggregation link,
event, or return that is not present below.

SERIALIZATION / DSCSA DATA (caller-supplied — verify against the controlled
serialization/EPCIS systems before acting):
{request_text}

{wiki_context}

Produce a review with:

## Aggregation integrity
- Each packaging tier and its parent-child link status; name every broken link

## Traceability event coverage
- Each required EPCIS event / trading-partner element and whether it is present

## Saleable-return verification
- Whether each saleable return is verified at the unit level before resale

## Interoperability readiness
- Whether the system supports enhanced unit-level traceability and exchange

## Gaps and recommendations
- Specific, closeable gaps (which tier, which event, which return)

## Claims
- Specific factual claims about the serialization configuration that ground the review
"""

_REVISION_PROMPT = """\
Revise the serialization / DSCSA traceability review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact aggregation tier, EPCIS event, or saleable
return from the supplied configuration; do not assert one not in the input.
"""


@dataclass
class SerializationDSCSARequest:
    """Structured input for the serialization / DSCSA traceability review workflow."""

    product_description: str
    """Generic product category and packaging levels."""

    serialization_scheme: str
    """GTIN + serial + lot + expiry encoding (2D DataMatrix)."""

    aggregation_summary: str
    """Parent-child aggregation across item / case / pallet."""

    epcis_events: str
    """Commissioning / packing / shipping event capture."""

    trading_partner_exchange: str
    """How EPCIS data is exchanged with authorized trading partners."""

    verification_process: str
    """Product-identifier verification for suspect / returned product."""

    saleable_returns_process: str
    """Verification of saleable returns before resale."""

    interoperability_status: str
    """Readiness for enhanced unit-level traceability."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Serialization scheme: {self.serialization_scheme[:cap]}",
            f"Aggregation summary: {self.aggregation_summary[:cap]}",
            f"EPCIS events: {self.epcis_events[:cap]}",
            f"Trading partner exchange: {self.trading_partner_exchange[:cap]}",
            f"Verification process: {self.verification_process[:cap]}",
            f"Saleable returns process: {self.saleable_returns_process[:cap]}",
            f"Interoperability status: {self.interoperability_status[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "AGGREGATION FLAGS:",
    "TRACEABILITY FLAGS:",
    "SALEABLE-RETURN FLAGS:",
)


class SerializationDSCSAWorkflow(BaseWorkflow):
    """
    Adversarial serialization / DSCSA traceability review: executor reviews the
    serialization scheme, aggregation, and EPCIS/verification coverage → reviewer
    challenges a broken aggregation link, a missing traceability event, and a
    saleable return processed without verification → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero AGGREGATION FLAGS
        AND zero TRACEABILITY FLAGS
        AND zero SALEABLE-RETURN FLAGS

    No reviewer veto — serialization-configuration corrections are reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: SerializationDSCSARequest,
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
                criteria=_SERIALIZATION_REVIEW_CRITERIA,
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

        serialization_checklist = self._build_serialization_checklist(
            request, accumulated
        )

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "product_description": sanitize_for_prompt(
                    request.product_description, max_chars=200
                ),
                "aggregation_flags": list(
                    dict.fromkeys(accumulated["AGGREGATION FLAGS:"])
                ),
                "traceability_flags": list(
                    dict.fromkeys(accumulated["TRACEABILITY FLAGS:"])
                ),
                "saleable_return_flags": list(
                    dict.fromkeys(accumulated["SALEABLE-RETURN FLAGS:"])
                ),
                "serialization_checklist": serialization_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "AGGREGATION FLAGS:": (
                "⚠️  AGGREGATION FLAGS (name the broken or missing parent-child "
                "aggregation link across packaging tiers):"
            ),
            "TRACEABILITY FLAGS:": (
                "⚠️  TRACEABILITY FLAGS (name the missing EPCIS event or trading-"
                "partner data element that breaks unit-level traceability):"
            ),
            "SALEABLE-RETURN FLAGS:": (
                "⚠️  SALEABLE-RETURN FLAGS (name the saleable return processed "
                "without product-identifier verification):"
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
    def _build_serialization_checklist(
        request: SerializationDSCSARequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Serialization / Supply-Chain Compliance]"]
        if accumulated["AGGREGATION FLAGS:"]:
            checklist.append(
                "[ ] Repair every flagged parent-child aggregation link across the "
                "packaging hierarchy"
            )
        if accumulated["TRACEABILITY FLAGS:"]:
            checklist.append(
                "[ ] Add every missing EPCIS event / trading-partner data element "
                "to restore unit-level traceability"
            )
        if accumulated["SALEABLE-RETURN FLAGS:"]:
            checklist.append(
                "[ ] Verify every flagged saleable return at the product-identifier "
                "level before resale"
            )
        checklist.extend([
            "[ ] Confirm every packaging tier has an intact parent-child aggregation link",
            "[ ] Confirm every required EPCIS event and trading-partner element is present",
            "[ ] Confirm saleable returns are verified at the unit level before resale",
            "[ ] Obtain Supply-Chain Compliance sign-off before any traceability filing",
        ])
        return checklist
