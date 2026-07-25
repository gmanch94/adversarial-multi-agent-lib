"""
Workflow — Viral-Vector Genome-Safety Characterization Audit (Lifesciences ·
Advanced Therapies / CGT)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to the genome-safety
characterization of a vector-based cell or gene therapy: executor summarises the
replication-competent-virus (RCR/RCL) testing, integration profile, and
insertional-mutagenesis / oncogenicity risk case; reviewer (cross-model per ARIS
§2.1) challenges an RCR/RCL strategy too insensitive for the vector class, an
integration/clonality assessment insufficient to characterise insertional-
mutagenesis risk, and an oncogenicity case or long-term-follow-up plan inadequate
for the risk profile.

No reviewer veto (D-LIFESCI-6): this audits whether the vector-safety
CHARACTERISATION STRATEGY is adequate — it is not the release gate. A positive
RCR/RCL result or an oncogenicity signal is a QC lot-release / disposition
failure against specification (see CGTLotReleaseSpecWorkflow), not an adversarial-
review halt. No-veto here does not dismiss vector risk; it scopes the workflow to
characterisation-adequacy gap-finding.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Vector-characterisation LIMS — RCR/RCL, integration-site, and copy-number
       results should resolve against the controlled characterisation LIMS, not
       caller-pasted summaries.
    2. Integration-site-sequencing data — clonality / insertional-mutagenesis
       assessment should read the controlled sequencing dataset, not a narrative.
    3. Nonclinical biodistribution / tumorigenicity study database — the safety
       case should reconcile against controlled study reports with GLP status.
    4. Long-term-follow-up registry — the follow-up plan should map into the
       controlled LTFU registry with enrolment commitments.
    5. Qualified Biosafety approver gate — every AI-suggested characterisation
       conclusion must be confirmed by a qualified Biosafety / Nonclinical Safety
       reviewer. Output is never auto-released.
    6. Dedicated third-model safety auditor — production should use a separately
       configured auditor model for risk-minimisation bias detection. See
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
    "ADVISORY ONLY — This AI-generated vector-safety characterisation audit is "
    "decision-support, not a regulatory submission and not a lot-release of "
    "record. A qualified Biosafety / Nonclinical Safety reviewer must "
    "independently confirm the RCR/RCL, integration, and oncogenicity case "
    "against the controlled study data before any conclusion. Not legal or "
    "medical advice."
)

_VECTOR_SAFETY_REVIEW_CRITERIA = """\
Evaluate this vector-safety characterisation audit on five dimensions. Score each 0–10.

1. RCR/RCL TESTING ADEQUACY (30%) — CRITICAL
   Is the replication-competent retrovirus/lentivirus (RCR/RCL) testing strategy
   and sensitivity adequate for the vector class and dose? Penalise a strategy
   too insensitive, wrong-stage, or missing for the vector type. Flag under
   RCR-RCL-RISK FLAGS:.

2. INTEGRATION / INSERTIONAL-MUTAGENESIS (25%) — CRITICAL
   Is the integration-site / clonality assessment sufficient to characterise
   insertional-mutagenesis risk (integration profile, vector copy number,
   clonal-expansion monitoring)? Penalise gaps. Flag under
   INSERTIONAL-MUTAGENESIS FLAGS:.

3. ONCOGENICITY / TUMORIGENICITY (20%) — CRITICAL
   Is the oncogenicity / tumorigenicity evidence and the long-term-follow-up
   plan adequate for the risk profile? Penalise an under-powered or absent
   tumorigenicity case. Flag under ONCOGENICITY FLAGS:.

4. BIODISTRIBUTION & LONG-TERM FOLLOW-UP (15%)
   Do the nonclinical biodistribution data and the LTFU plan cover the persistence
   and shedding profile of the vector? Penalise unaddressed persistence.

5. ACTIONABILITY (10%)
   Is each gap specific enough for Biosafety to close (which assay, which endpoint,
   what sensitivity)? Penalise vague findings.

Overall score = weighted average.
Score >= 7.5 AND zero RCR-RCL-RISK FLAGS AND zero INSERTIONAL-MUTAGENESIS FLAGS
AND zero ONCOGENICITY FLAGS: ready for Biosafety sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  RCR-RCL-RISK FLAGS: [bullet list, or "None detected"]
  INSERTIONAL-MUTAGENESIS FLAGS: [bullet list, or "None detected"]
  ONCOGENICITY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are auditing the genome-safety characterisation of a vector-based cell or
gene therapy for a Biosafety / Nonclinical Safety reviewer. You have no stake in
the outcome. Assess the RCR/RCL testing, integration profile, and
insertional-mutagenesis / oncogenicity case against the supplied data — not
against general norms.

BASE EVERY FINDING ON THE INPUT DATA ONLY. Do not assert a safety conclusion not
grounded in the vector-characterisation, integration, biodistribution, or
follow-up data below.

VECTOR-SAFETY DATA (caller-supplied — verify against the characterisation LIMS
before acting):
{request_text}

{wiki_context}

Produce an audit with:

## RCR/RCL testing
State whether the replication-competent-virus testing strategy and sensitivity
are adequate for the vector class and dose; name any gap.

## Integration and insertional-mutagenesis
Assess the integration profile, vector copy number, and clonality monitoring;
name any gap in the insertional-mutagenesis characterisation.

## Oncogenicity and tumorigenicity
Assess the oncogenicity / tumorigenicity evidence and its sufficiency for the
risk profile.

## Biodistribution and long-term follow-up
Assess whether biodistribution and the LTFU plan cover vector persistence and
shedding.

## Gaps and recommendations
Specific, closeable gaps (which assay, which endpoint, what sensitivity).

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this vector-safety characterisation audit based on reviewer critique.

ORIGINAL AUDIT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact missing assay, endpoint, or sensitivity
from the supplied data; do not assert a characterisation not present in the input.
"""


@dataclass
class VectorSafetyRequest:
    """Structured input for the viral-vector genome-safety characterisation audit."""

    vector_description: str
    """Vector class and construct (e.g. a gamma-retroviral, lentiviral, or AAV vector)."""

    rcr_rcl_testing_summary: str
    """Replication-competent-virus (RCR/RCL) testing strategy, method, and sensitivity."""

    integration_profile_data: str
    """Integration-site distribution / clonality data."""

    insertional_mutagenesis_assessment: str
    """Insertional-mutagenesis risk assessment and monitoring plan."""

    oncogenicity_or_tumorigenicity_data: str
    """Oncogenicity / tumorigenicity study evidence."""

    vector_copy_number: str
    """Vector copy number per cell and its acceptance criterion."""

    nonclinical_biodistribution: str
    """Nonclinical biodistribution / persistence data."""

    long_term_followup_plan: str
    """Long-term-follow-up (LTFU) plan and duration."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Vector description: {self.vector_description[:cap]}",
            f"RCR/RCL testing summary: {self.rcr_rcl_testing_summary[:cap]}",
            f"Integration profile data: {self.integration_profile_data[:cap]}",
            f"Insertional-mutagenesis assessment: {self.insertional_mutagenesis_assessment[:cap]}",
            f"Oncogenicity / tumorigenicity data: {self.oncogenicity_or_tumorigenicity_data[:cap]}",
            f"Vector copy number: {self.vector_copy_number[:cap]}",
            f"Nonclinical biodistribution: {self.nonclinical_biodistribution[:cap]}",
            f"Long-term follow-up plan: {self.long_term_followup_plan[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "RCR-RCL-RISK FLAGS:",
    "INSERTIONAL-MUTAGENESIS FLAGS:",
    "ONCOGENICITY FLAGS:",
)


class VectorSafetyWorkflow(BaseWorkflow):
    """
    Adversarial viral-vector genome-safety characterisation audit: executor
    summarises the RCR/RCL, integration, and oncogenicity case → reviewer
    challenges an insensitive RCR/RCL strategy, an insufficient
    insertional-mutagenesis assessment, and an inadequate oncogenicity case →
    iterate.

    Convergence gate:
        score ≥ threshold
        AND zero RCR-RCL-RISK FLAGS
        AND zero INSERTIONAL-MUTAGENESIS FLAGS
        AND zero ONCOGENICITY FLAGS

    No reviewer veto — this is characterisation-adequacy gap-finding, not the
    release gate; a positive RCR/RCL or oncogenicity finding is a QC lot-release
    disposition action (see CGTLotReleaseSpecWorkflow), not an adversarial halt.
    """

    async def run(  # type: ignore[override]
        self,
        request: VectorSafetyRequest,
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
                criteria=_VECTOR_SAFETY_REVIEW_CRITERIA,
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

        vector_safety_checklist = self._build_vector_safety_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "vector_description": sanitize_for_prompt(
                    request.vector_description, max_chars=200
                ),
                "rcr_rcl_risk_flags": list(dict.fromkeys(accumulated["RCR-RCL-RISK FLAGS:"])),
                "insertional_mutagenesis_flags": list(
                    dict.fromkeys(accumulated["INSERTIONAL-MUTAGENESIS FLAGS:"])
                ),
                "oncogenicity_flags": list(dict.fromkeys(accumulated["ONCOGENICITY FLAGS:"])),
                "vector_safety_checklist": vector_safety_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "RCR-RCL-RISK FLAGS:": (
                "⚠️  RCR-RCL-RISK FLAGS (cite the missing or insensitive "
                "replication-competent-virus assay for the named vector class):"
            ),
            "INSERTIONAL-MUTAGENESIS FLAGS:": (
                "⚠️  INSERTIONAL-MUTAGENESIS FLAGS (cite the missing integration / "
                "clonality endpoint for the named risk):"
            ),
            "ONCOGENICITY FLAGS:": (
                "⚠️  ONCOGENICITY FLAGS (cite the missing tumorigenicity evidence or "
                "long-term-follow-up commitment):"
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
    def _build_vector_safety_checklist(
        request: VectorSafetyRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Biosafety / Nonclinical Safety]"]
        if accumulated["RCR-RCL-RISK FLAGS:"]:
            checklist.append(
                "[ ] Close every flagged RCR/RCL gap with a validated, "
                "vector-class-appropriate assay before release"
            )
        if accumulated["INSERTIONAL-MUTAGENESIS FLAGS:"]:
            checklist.append(
                "[ ] Supply the missing integration-site / clonality data for each "
                "flagged insertional-mutagenesis gap"
            )
        if accumulated["ONCOGENICITY FLAGS:"]:
            checklist.append(
                "[ ] Provide the tumorigenicity evidence or LTFU commitment for each "
                "flagged oncogenicity gap"
            )
        checklist.extend([
            "[ ] Confirm the RCR/RCL testing sensitivity is appropriate for the vector class",
            "[ ] Confirm integration / copy-number data characterise insertional-mutagenesis risk",
            "[ ] Confirm the long-term-follow-up plan covers vector persistence and shedding",
            "[ ] Obtain Biosafety / Nonclinical Safety sign-off before release",
        ])
        return checklist
