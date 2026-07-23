"""
Workflow — Assay Performance-Claim Review (Lifesciences · Diagnostics, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to IVD assay
performance-claim review: executor maps each sensitivity / specificity /
interference claim to the underlying study data; reviewer (cross-model per
ARIS §2.1) challenges any point-estimate claim that ignores the study CI, any
overstated specificity, and any claimed matrix with untested interferents, with
the power to VETO when a claim the study data cannot support risks misdiagnosis
or an adulteration/misbranding exposure.

Veto gate (D-LIFESCI-2): fires when a performance claim is overstated enough
that releasing it would create a misdiagnosis risk or an adulteration /
misbranding exposure — a claim the data cannot support in the claimed
intended-use population.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. LIMS integration — raw analytical study results should resolve against
       the controlled laboratory-information-management system, not
       caller-pasted summaries.
    2. CLSI EP-protocol study database — sensitivity / specificity / precision
       claims should reconcile against the controlled CLSI EP study records
       (EP05 / EP07 / EP12 / EP17), not caller-supplied text.
    3. Clinical-study database — every clinical-performance claim should
       reconcile against the controlled clinical-study database and its CIs.
    4. Labeling-management system — released performance claims must resolve
       against the controlled labeling-management system before any IVD label
       or IFU is issued.
    5. Dedicated third-model claim auditor — production should use a separately
       configured auditor model for claim-inflation bias detection. See
       ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated assay performance-claim review is "
    "decision-support, not IVD labeling and not a regulatory submission. A "
    "qualified Diagnostics Regulatory / R&D reviewer must independently verify "
    "every performance claim against the underlying study data before any label "
    "is released. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer identified "
    "a performance claim the study data do not support to a degree that risks "
    "misdiagnosis or an adulteration/misbranding exposure. See "
    "metadata['veto_reason']. Escalate to Diagnostics Regulatory; do not release "
    "the claim."
)

_FLAG_HEADERS = ("SENSITIVITY-CLAIM FLAGS:", "SPECIFICITY-CLAIM FLAGS:", "INTERFERENCE FLAGS:")

_ASSAY_REVIEW_CRITERIA = """\
Evaluate this assay performance-claim review on five dimensions. Score each 0–10.

1. SENSITIVITY-CLAIM SUPPORT (30%) — CRITICAL
   Does each clinical/analytical sensitivity claim stay within what the study n
   and its confidence interval support? Penalise a point-estimate claim that
   ignores the lower CI bound or an underpowered n. Flag under
   SENSITIVITY-CLAIM FLAGS:.

2. SPECIFICITY-CLAIM SUPPORT (25%) — CRITICAL
   Is the specificity / false-positive-rate claim supported by the data and its
   CI? Penalise an overstated specificity claim. Flag under SPECIFICITY-CLAIM FLAGS:.

3. INTERFERENCE / CROSS-REACTIVITY (20%) — CRITICAL
   Are interferents and cross-reactants tested for every claimed matrix and
   population? Penalise a claimed matrix with untested interferents. Flag under
   INTERFERENCE FLAGS:.

4. STUDY-DESIGN ADEQUACY (15%)
   Is the study design adequate (CLSI EP protocol, appropriate reference method,
   representative population) to support the claim set? Penalise design gaps.

5. ACTIONABILITY (10%)
   Is each finding specific enough for R&D to resolve (which claim, which study,
   which interferent)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a performance claim is overstated enough that releasing it would
create a misdiagnosis risk or an adulteration/misbranding exposure (a claim the
data cannot support in the claimed intended-use population).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SENSITIVITY-CLAIM FLAGS AND zero SPECIFICITY-CLAIM FLAGS
AND zero INTERFERENCE FLAGS AND no VETO: ready for Diagnostics Regulatory
sign-off. Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SENSITIVITY-CLAIM FLAGS: [bullet list, or "None detected"]
  SPECIFICITY-CLAIM FLAGS: [bullet list, or "None detected"]
  INTERFERENCE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are conducting an assay performance-claim review for a qualified Diagnostics
Regulatory / R&D reviewer. You have no stake in the outcome. Your job is to map
each proposed performance claim to the underlying study data, assess whether the
claim stays within the study confidence interval and tested matrices, and
recommend a defensible claim set, grounded only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

ASSAY PERFORMANCE-CLAIM DATA:
{request_text}

{wiki_context}

Produce a structured assay performance-claim review with exactly these sections:

## Claim-by-claim data mapping
Map each proposed claim to the specific study, n, and confidence interval that
supports it. State the source study for each claim.

## Sensitivity assessment
For each sensitivity claim, compare the point estimate against the study n and
lower CI bound. State whether the claim is supported or overstated.

## Specificity assessment
For each specificity / false-positive-rate claim, compare against the data and
its CI. State whether the claim is supported or overstated.

## Interference and cross-reactivity
For each claimed matrix and population, state whether interferents and
cross-reactants were tested. Identify any claimed matrix with untested
interferents.

## Recommended claim set
State the defensible claim set: each performance claim re-stated within the
study CI and restricted to the tested matrix/population.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this assay performance-claim review. Address EVERY issue in the reviewer's
critique, especially any SENSITIVITY-CLAIM FLAGS, SPECIFICITY-CLAIM FLAGS, or
INTERFERENCE FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SENSITIVITY/SPECIFICITY flag: re-state the claim within the study
CI, or remove it.
⚠️  For any INTERFERENCE flag: restrict the claimed matrix/population to what
was tested.
"""


@dataclass
class AssayClaimRequest:
    """Structured input for the assay performance-claim review workflow."""

    assay_description: str
    """Generic category and format of the assay (e.g. a rapid antigen test)."""

    intended_use: str
    """Intended-use statement: measurand, population, matrix, clinical purpose."""

    analyte_measurand: str
    """The analyte / measurand and its measurement principle."""

    claim_set: str
    """Proposed performance claims (sensitivity, specificity, precision, etc.)."""

    study_design_summary: str
    """Study design: CLSI EP protocol, n, reference method, population."""

    interference_panel_tested: str
    """Interferents tested and the matrices/populations they were tested in."""

    cross_reactivity_data: str
    """Cross-reactants tested and the results observed."""

    stability_claims: str
    """Shelf-life / in-use / transport stability claims and supporting data."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Assay description: {self.assay_description[:cap]}",
            f"Intended use: {self.intended_use[:cap]}",
            f"Analyte / measurand: {self.analyte_measurand[:cap]}",
            f"Claim set: {self.claim_set[:cap]}",
            f"Study design summary: {self.study_design_summary[:cap]}",
            f"Interference panel tested: {self.interference_panel_tested[:cap]}",
            f"Cross-reactivity data: {self.cross_reactivity_data[:cap]}",
            f"Stability claims: {self.stability_claims[:cap]}",
        ])


class AssayPerformanceClaimWorkflow(BaseWorkflow):
    """
    Adversarial assay performance-claim review: executor maps each performance
    claim to the underlying study data → reviewer challenges point-estimate
    claims that ignore the study CI, overstated specificity, and claimed
    matrices with untested interferents, with the power to VETO → iterate.

    Convergence gate (D-LIFESCI-2):
        score ≥ threshold (8.0)
        AND zero SENSITIVITY-CLAIM FLAGS
        AND zero SPECIFICITY-CLAIM FLAGS
        AND zero INTERFERENCE FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: AssayClaimRequest,
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
                criteria=_ASSAY_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            # Audit-trail writes happen BEFORE the veto check — preserves the
            # round-N draft in wiki + ledger even if vetoed (D-LIFESCI-2).
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

        assay_checklist = self._build_assay_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "assay_description": sanitize_for_prompt(
                request.assay_description, max_chars=200
            ),
            "sensitivity_claim_flags": list(
                dict.fromkeys(accumulated["SENSITIVITY-CLAIM FLAGS:"])
            ),
            "specificity_claim_flags": list(
                dict.fromkeys(accumulated["SPECIFICITY-CLAIM FLAGS:"])
            ),
            "interference_flags": list(
                dict.fromkeys(accumulated["INTERFERENCE FLAGS:"])
            ),
            "assay_checklist": assay_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the Diagnostics Regulatory reviewer sees what the AI produced
            # before the REVIEWER VETO banner was prepended.
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
            "SENSITIVITY-CLAIM FLAGS:": (
                "⚠️  SENSITIVITY-CLAIM FLAGS (re-state each claim within the study "
                "confidence interval and n, or remove it):"
            ),
            "SPECIFICITY-CLAIM FLAGS:": (
                "⚠️  SPECIFICITY-CLAIM FLAGS (re-state each specificity / "
                "false-positive-rate claim within the data and its CI, or remove "
                "it):"
            ),
            "INTERFERENCE FLAGS:": (
                "⚠️  INTERFERENCE FLAGS (restrict each claimed matrix / population "
                "to the interferents and cross-reactants actually tested):"
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
    def _build_assay_checklist(
        request: AssayClaimRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Diagnostics Regulatory + R&D]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — do not release the claim; escalate to "
                "Diagnostics Regulatory before any label is issued"
            )
        sensitivity_flags = accumulated.get("SENSITIVITY-CLAIM FLAGS:", [])
        specificity_flags = accumulated.get("SPECIFICITY-CLAIM FLAGS:", [])
        interference_flags = accumulated.get("INTERFERENCE FLAGS:", [])
        if sensitivity_flags:
            checklist.append(
                f"[ ] ⚠️  SENSITIVITY-CLAIM FLAGS ({len(sensitivity_flags)}) — "
                "re-state each claim within the study CI and n"
            )
        if specificity_flags:
            checklist.append(
                f"[ ] ⚠️  SPECIFICITY-CLAIM FLAGS ({len(specificity_flags)}) — "
                "re-state each specificity claim within the data and its CI"
            )
        if interference_flags:
            checklist.append(
                f"[ ] ⚠️  INTERFERENCE FLAGS ({len(interference_flags)}) — "
                "restrict each claimed matrix to the interferents actually tested"
            )
        checklist.extend([
            "[ ] Re-state every performance claim within the study confidence interval",
            "[ ] Restrict each claimed matrix/population to the tested interferents",
            "[ ] Confirm the CLSI EP study design supports the released claim set",
            "[ ] Obtain Diagnostics Regulatory sign-off before any label is released",
        ])
        return checklist
