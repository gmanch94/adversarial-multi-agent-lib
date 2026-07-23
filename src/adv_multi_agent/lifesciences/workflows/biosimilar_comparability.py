"""
Workflow — Biosimilar Comparability Assessment (Lifesciences · Pharma, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to biosimilar
analytical/clinical comparability: executor assesses analytical similarity,
residual uncertainty, and bridging/extrapolation for a proposed biosimilar;
reviewer (cross-model per ARIS §2.1) challenges any under-demonstrated critical
quality attribute, understated residual uncertainty, and unjustified bridging,
with the power to VETO a biosimilarity conclusion the comparability data do not
support.

Veto gate (D-LIFESCI-4): fires when a biosimilarity conclusion (or indication
extrapolation) is asserted while a critical quality attribute is NOT demonstrated
analytically similar and the residual uncertainty is unresolved.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Analytical-characterization data systems — the structural/functional
       characterization should resolve against the controlled analytical data
       systems, not caller-pasted text.
    2. Comparative-study data management — PK/PD and clinical/immunogenicity data
       should resolve against the controlled study-data system.
    3. Quality-attribute risk-ranking framework — CQA tiering should come from
       the controlled risk-ranking framework, not a manual summary.
    4. Regulatory comparability-dossier system — the comparability conclusion
       should resolve against the controlled submission repository.
    5. Qualified approver gate — every AI-suggested comparability conclusion must
       be reviewed by qualified Biosimilar Development and Regulatory Affairs.
       Output is never an auto-concluded biosimilarity determination.
    6. Dedicated third-model comparability auditor — production should use a
       separately configured auditor model for analytical-similarity bias
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
    "ADVISORY ONLY — This AI-generated biosimilar comparability assessment is "
    "decision-support, not a biosimilarity determination and not a regulatory "
    "submission. Qualified Biosimilar Development and Regulatory Affairs must "
    "independently confirm the analytical similarity, residual uncertainty, and "
    "bridging before any biosimilarity conclusion is made. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "biosimilarity conclusion asserted while a critical quality attribute is not "
    "analytically similar and the residual uncertainty is unresolved. See "
    "metadata['veto_reason']. Escalate to Regulatory Affairs; biosimilarity must "
    "not be concluded until the analytical-similarity gap and residual uncertainty "
    "are resolved."
)

_FLAG_HEADERS = (
    "ANALYTICAL-SIMILARITY FLAGS:",
    "RESIDUAL-UNCERTAINTY FLAGS:",
    "BRIDGING FLAGS:",
)

_BIOSIMILAR_REVIEW_CRITERIA = """\
Evaluate this biosimilar comparability assessment on five dimensions. Score each 0–10.

1. ANALYTICAL SIMILARITY (30%) — CRITICAL
   Is every critical quality attribute (CQA) demonstrated analytically similar to
   the reference product within a justified range? Penalise a CQA not demonstrated
   similar. Flag under ANALYTICAL-SIMILARITY FLAGS:.

2. RESIDUAL-UNCERTAINTY RESOLUTION (25%) — CRITICAL
   Is the residual uncertainty after analytical/functional data honestly stated
   and resolved by the totality of evidence (PK/PD, clinical, immunogenicity)?
   Penalise understated or unresolved residual uncertainty. Flag under
   RESIDUAL-UNCERTAINTY FLAGS:.

3. BRIDGING & EXTRAPOLATION (20%) — CRITICAL
   Is every bridging step and every extrapolated indication justified by the
   comparability data? Penalise an unjustified bridge or extrapolation. Flag under
   BRIDGING FLAGS:.

4. TOTALITY-OF-EVIDENCE COHERENCE (15%)
   Is the stepwise evidence integrated into a coherent totality-of-evidence
   argument? Penalise a conclusion that ignores a weak step.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which CQA, which study, which
   indication)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a biosimilarity conclusion (or indication extrapolation) is
asserted while a critical quality attribute is not demonstrated analytically
similar and the residual uncertainty is unresolved.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero ANALYTICAL-SIMILARITY FLAGS AND zero RESIDUAL-UNCERTAINTY
FLAGS AND zero BRIDGING FLAGS AND no VETO: ready for Regulatory Affairs sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  ANALYTICAL-SIMILARITY FLAGS: [bullet list, or "None detected"]
  RESIDUAL-UNCERTAINTY FLAGS: [bullet list, or "None detected"]
  BRIDGING FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are producing a biosimilar comparability assessment for qualified Biosimilar
Development and Regulatory Affairs approvers. You have no stake in the outcome.
Assess analytical similarity of the critical quality attributes, the residual
uncertainty, and the bridging/extrapolation — grounded only in the data supplied.

BASE THE ASSESSMENT ON THE INPUT DATA ONLY.

BIOSIMILAR COMPARABILITY DATA:
{request_text}

{wiki_context}

Produce a structured assessment with exactly these sections:

## Analytical-similarity summary
State, for each critical quality attribute, whether it is demonstrated
analytically similar to the reference. Do not claim similarity a CQA does not show.

## Residual-uncertainty assessment
State the residual uncertainty after analytical/functional data and whether the
totality of evidence resolves it.

## Bridging and extrapolation
State whether each bridging step and extrapolated indication is justified.

## Totality-of-evidence conclusion
State the comparability conclusion grounded in the integrated stepwise evidence.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this biosimilar comparability assessment. Address EVERY issue in the
reviewer's critique, especially any ANALYTICAL-SIMILARITY FLAGS, RESIDUAL-
UNCERTAINTY FLAGS, or BRIDGING FLAGS.

PREVIOUS ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any ANALYTICAL-SIMILARITY flag: do not claim similarity a CQA does not demonstrate.
⚠️  For any RESIDUAL-UNCERTAINTY flag: state the uncertainty and how the evidence resolves it.
⚠️  For any BRIDGING flag: justify or withdraw the bridge/extrapolation.
"""


@dataclass
class BiosimilarComparabilityRequest:
    """Structured input for the biosimilar comparability assessment workflow."""

    product_description: str
    """Generic proposed-biosimilar and reference-product category."""

    analytical_similarity_summary: str
    """Structural / functional characterization vs the reference."""

    quality_attributes: str
    """Critical quality attributes and their risk tiering."""

    pk_pd_summary: str
    """Comparative PK / PD study results."""

    clinical_comparability_summary: str
    """Comparative clinical / immunogenicity data."""

    residual_uncertainty: str
    """Caller's stated residual uncertainty after analytical/functional data."""

    bridging_summary: str
    """Bridging across reference-product sources / indications."""

    extrapolation_indications: str
    """Indications sought by extrapolation without direct study."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Analytical similarity summary: {self.analytical_similarity_summary[:cap]}",
            f"Quality attributes: {self.quality_attributes[:cap]}",
            f"PK/PD summary: {self.pk_pd_summary[:cap]}",
            f"Clinical comparability summary: {self.clinical_comparability_summary[:cap]}",
            f"Residual uncertainty: {self.residual_uncertainty[:cap]}",
            f"Bridging summary: {self.bridging_summary[:cap]}",
            f"Extrapolation indications: {self.extrapolation_indications[:cap]}",
        ])


class BiosimilarComparabilityWorkflow(BaseWorkflow):
    """
    Adversarial biosimilar comparability assessment: executor assesses analytical
    similarity, residual uncertainty, and bridging → reviewer challenges an
    under-demonstrated CQA, understated residual uncertainty, and unjustified
    bridging, with the power to VETO → iterate.

    Convergence gate (D-LIFESCI-4):
        score ≥ threshold (8.0)
        AND zero ANALYTICAL-SIMILARITY FLAGS
        AND zero RESIDUAL-UNCERTAINTY FLAGS
        AND zero BRIDGING FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: BiosimilarComparabilityRequest,
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
                criteria=_BIOSIMILAR_REVIEW_CRITERIA,
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

        biosimilar_checklist = self._build_biosimilar_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "analytical_similarity_flags": list(
                dict.fromkeys(accumulated["ANALYTICAL-SIMILARITY FLAGS:"])
            ),
            "residual_uncertainty_flags": list(
                dict.fromkeys(accumulated["RESIDUAL-UNCERTAINTY FLAGS:"])
            ),
            "bridging_flags": list(dict.fromkeys(accumulated["BRIDGING FLAGS:"])),
            "biosimilar_checklist": biosimilar_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the approver sees what the AI produced before the REVIEWER VETO
            # banner was prepended.
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
            "ANALYTICAL-SIMILARITY FLAGS:": (
                "⚠️  ANALYTICAL-SIMILARITY FLAGS (do not claim similarity a CQA "
                "does not demonstrate):"
            ),
            "RESIDUAL-UNCERTAINTY FLAGS:": (
                "⚠️  RESIDUAL-UNCERTAINTY FLAGS (state the uncertainty and how the "
                "evidence resolves it):"
            ),
            "BRIDGING FLAGS:": (
                "⚠️  BRIDGING FLAGS (justify or withdraw the bridge/extrapolation):"
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
    def _build_biosimilar_checklist(
        request: BiosimilarComparabilityRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Biosimilar Development / Regulatory Affairs]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — a biosimilarity conclusion is asserted "
                "while a CQA is not analytically similar; escalate to Regulatory "
                "Affairs and do not conclude biosimilarity until resolved"
            )
        analytical_flags = accumulated.get("ANALYTICAL-SIMILARITY FLAGS:", [])
        residual_flags = accumulated.get("RESIDUAL-UNCERTAINTY FLAGS:", [])
        bridging_flags = accumulated.get("BRIDGING FLAGS:", [])
        if analytical_flags:
            checklist.append(
                f"[ ] ⚠️  ANALYTICAL-SIMILARITY FLAGS ({len(analytical_flags)}) — "
                "demonstrate or withdraw similarity for each flagged CQA"
            )
        if residual_flags:
            checklist.append(
                f"[ ] ⚠️  RESIDUAL-UNCERTAINTY FLAGS ({len(residual_flags)}) — "
                "resolve each stated residual uncertainty with evidence"
            )
        if bridging_flags:
            checklist.append(
                f"[ ] ⚠️  BRIDGING FLAGS ({len(bridging_flags)}) — justify or "
                "withdraw each bridge/extrapolation"
            )
        checklist.extend([
            "[ ] Demonstrate analytical similarity for every critical quality attribute",
            "[ ] Resolve the residual uncertainty with the totality of evidence",
            "[ ] Justify every bridging step and extrapolated indication",
            "[ ] Obtain Regulatory Affairs sign-off before any biosimilarity conclusion",
        ])
        return checklist
