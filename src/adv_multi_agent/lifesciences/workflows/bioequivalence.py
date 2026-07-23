"""
Workflow — Bioequivalence Assessment (Lifesciences · Pharma, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to a bioequivalence
assessment: executor assesses PK boundary conformance, study-design validity, and
waiver/limit justification for a test-vs-reference product; reviewer (cross-model
per ARIS §2.1) challenges a PK confidence interval outside the limits, an
inappropriate study design, and an unjustified biowaiver, with the power to VETO
a bioequivalence conclusion the data do not support.

Veto gate (D-LIFESCI-4): fires when a bioequivalence conclusion is asserted while
a PK parameter's 90% confidence interval falls outside the applicable limits (or a
required study / tightened limit is absent).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Clinical-pharmacology / PK-analysis system — the PK parameters and
       confidence intervals should resolve against the controlled PK-analysis
       system, not caller-pasted text.
    2. Bioanalytical LIMS — the concentration data underpinning the PK should
       resolve against the controlled bioanalytical LIMS.
    3. Statistical bioequivalence-analysis software — the ANOVA / replicate
       analysis should be produced by the controlled statistical system.
    4. Regulatory-submission system — the bioequivalence conclusion should resolve
       against the controlled submission repository.
    5. Qualified approver gate — every AI-suggested bioequivalence conclusion must
       be reviewed by qualified Clinical Pharmacology / Regulatory. Output is
       never an auto-concluded bioequivalence determination.
    6. Dedicated third-model bioequivalence auditor — production should use a
       separately configured auditor model for PK-boundary bias detection.
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
    "ADVISORY ONLY — This AI-generated bioequivalence assessment is "
    "decision-support, not a bioequivalence determination and not a regulatory "
    "submission. Qualified Clinical Pharmacology / Regulatory must independently "
    "confirm the PK boundary conformance, study design, and waiver justification "
    "before any bioequivalence conclusion is made. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "bioequivalence conclusion asserted while a PK parameter's 90% confidence "
    "interval falls outside the applicable limits. See metadata['veto_reason']. "
    "Escalate to Clinical Pharmacology / Regulatory; bioequivalence must not be "
    "concluded until the boundary failure is resolved."
)

_FLAG_HEADERS = (
    "PK-BOUNDARY FLAGS:",
    "STUDY-DESIGN FLAGS:",
    "WAIVER-JUSTIFICATION FLAGS:",
)

_BIOEQUIVALENCE_REVIEW_CRITERIA = """\
Evaluate this bioequivalence assessment on five dimensions. Score each 0–10.

1. PK-BOUNDARY CONFORMANCE (30%) — CRITICAL
   Does every pharmacokinetic parameter's 90% confidence interval fall within the
   applicable bioequivalence limits (typically 80.00-125.00%)? Penalise a CI
   outside the limits treated as equivalent. Flag under PK-BOUNDARY FLAGS:.

2. STUDY-DESIGN VALIDITY (25%) — CRITICAL
   Is the study design (condition, dosing, population, replicate design)
   appropriate to establish bioequivalence for this product? Penalise a design
   element inappropriate for the product. Flag under STUDY-DESIGN FLAGS:.

3. WAIVER / LIMIT JUSTIFICATION (20%) — CRITICAL
   Is every biowaiver or tightened/widened limit justified by the applicable
   criteria (BCS class, narrow-therapeutic-index, highly-variable drug)? Penalise
   an unjustified waiver or limit. Flag under WAIVER-JUSTIFICATION FLAGS:.

4. STATISTICAL RIGOR (15%)
   Are the intra-subject CV, replicate design, and outlier handling sound?
   Penalise weak statistical treatment.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which parameter, which design
   element, which criterion)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a bioequivalence conclusion is asserted while a PK parameter's 90%
confidence interval falls outside the applicable limits (or a required study /
tightened limit is absent). Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero PK-BOUNDARY FLAGS AND zero STUDY-DESIGN FLAGS AND zero
WAIVER-JUSTIFICATION FLAGS AND no VETO: ready for Clinical Pharmacology sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PK-BOUNDARY FLAGS: [bullet list, or "None detected"]
  STUDY-DESIGN FLAGS: [bullet list, or "None detected"]
  WAIVER-JUSTIFICATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are producing a bioequivalence assessment for qualified Clinical Pharmacology
/ Regulatory approvers. You have no stake in the outcome. Assess PK boundary
conformance, study-design validity, and waiver/limit justification — grounded
only in the data supplied.

BASE THE ASSESSMENT ON THE INPUT DATA ONLY.

BIOEQUIVALENCE DATA:
{request_text}

{wiki_context}

Produce a structured assessment with exactly these sections:

## PK-boundary conformance
State, for each PK parameter, whether the 90% confidence interval falls within
the applicable limits. Do not treat a CI outside the limits as equivalent.

## Study-design validity
State whether the design (condition, dosing, population, replicate design) is
appropriate for this product.

## Waiver and limit justification
State whether each biowaiver or tightened/widened limit is justified.

## Bioequivalence conclusion
State the conclusion grounded in the boundary and design assessment.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this bioequivalence assessment. Address EVERY issue in the reviewer's
critique, especially any PK-BOUNDARY FLAGS, STUDY-DESIGN FLAGS, or
WAIVER-JUSTIFICATION FLAGS.

PREVIOUS ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any PK-BOUNDARY flag: do not treat a CI outside the limits as equivalent.
⚠️  For any STUDY-DESIGN flag: correct the design element for this product.
⚠️  For any WAIVER-JUSTIFICATION flag: justify or withdraw the waiver/limit.
"""


@dataclass
class BioequivalenceRequest:
    """Structured input for the bioequivalence assessment workflow."""

    product_description: str
    """Generic test-vs-reference product category and dosage form."""

    study_design: str
    """Crossover / parallel, fasting / fed, single / multiple dose."""

    pk_parameters: str
    """Cmax, AUC and 90% CI results vs the 80.00-125.00% limits."""

    study_population: str
    """Subjects, sample size, healthy vs patient."""

    statistical_analysis: str
    """ANOVA, intra-subject CV, replicate design."""

    boundary_results: str
    """Whether any parameter's 90% CI touches / crosses a limit."""

    biowaiver_basis: str
    """BCS-based biowaiver claim, if any."""

    special_considerations: str
    """Narrow-therapeutic-index / highly-variable drug considerations."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Study design: {self.study_design[:cap]}",
            f"PK parameters: {self.pk_parameters[:cap]}",
            f"Study population: {self.study_population[:cap]}",
            f"Statistical analysis: {self.statistical_analysis[:cap]}",
            f"Boundary results: {self.boundary_results[:cap]}",
            f"Biowaiver basis: {self.biowaiver_basis[:cap]}",
            f"Special considerations: {self.special_considerations[:cap]}",
        ])


class BioequivalenceWorkflow(BaseWorkflow):
    """
    Adversarial bioequivalence assessment: executor assesses PK boundary
    conformance, study-design validity, and waiver justification → reviewer
    challenges a CI outside the limits, an inappropriate design, and an
    unjustified waiver, with the power to VETO → iterate.

    Convergence gate (D-LIFESCI-4):
        score ≥ threshold (8.0)
        AND zero PK-BOUNDARY FLAGS
        AND zero STUDY-DESIGN FLAGS
        AND zero WAIVER-JUSTIFICATION FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: BioequivalenceRequest,
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
                criteria=_BIOEQUIVALENCE_REVIEW_CRITERIA,
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

            if review.approved and not self._flag_classes_unresolved(
                review.critique, _FLAG_HEADERS, current.values()
            ):
                converged = True
                break

        bioequivalence_checklist = self._build_bioequivalence_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "pk_boundary_flags": list(dict.fromkeys(accumulated["PK-BOUNDARY FLAGS:"])),
            "study_design_flags": list(
                dict.fromkeys(accumulated["STUDY-DESIGN FLAGS:"])
            ),
            "waiver_justification_flags": list(
                dict.fromkeys(accumulated["WAIVER-JUSTIFICATION FLAGS:"])
            ),
            "bioequivalence_checklist": bioequivalence_checklist,
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
            "PK-BOUNDARY FLAGS:": (
                "⚠️  PK-BOUNDARY FLAGS (do not treat a CI outside the limits as "
                "equivalent):"
            ),
            "STUDY-DESIGN FLAGS:": (
                "⚠️  STUDY-DESIGN FLAGS (correct the design element for this "
                "product):"
            ),
            "WAIVER-JUSTIFICATION FLAGS:": (
                "⚠️  WAIVER-JUSTIFICATION FLAGS (justify or withdraw the "
                "waiver/limit):"
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
    def _build_bioequivalence_checklist(
        request: BioequivalenceRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Clinical Pharmacology / Regulatory]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — a bioequivalence conclusion is asserted "
                "while a PK 90% CI falls outside the limits; escalate to Clinical "
                "Pharmacology and do not conclude bioequivalence until resolved"
            )
        pk_flags = accumulated.get("PK-BOUNDARY FLAGS:", [])
        design_flags = accumulated.get("STUDY-DESIGN FLAGS:", [])
        waiver_flags = accumulated.get("WAIVER-JUSTIFICATION FLAGS:", [])
        if pk_flags:
            checklist.append(
                f"[ ] ⚠️  PK-BOUNDARY FLAGS ({len(pk_flags)}) — do not treat any CI "
                "outside the limits as equivalent"
            )
        if design_flags:
            checklist.append(
                f"[ ] ⚠️  STUDY-DESIGN FLAGS ({len(design_flags)}) — correct each "
                "inappropriate design element for this product"
            )
        if waiver_flags:
            checklist.append(
                f"[ ] ⚠️  WAIVER-JUSTIFICATION FLAGS ({len(waiver_flags)}) — justify "
                "or withdraw each waiver/limit"
            )
        checklist.extend([
            "[ ] Confirm every PK 90% CI falls within the applicable limits",
            "[ ] Confirm the study design is appropriate for this product",
            "[ ] Justify every biowaiver or tightened/widened limit",
            "[ ] Obtain Clinical Pharmacology sign-off before any bioequivalence conclusion",
        ])
        return checklist
