"""
Workflow — Cold-Chain Excursion Disposition (Lifesciences · Pharma/Diagnostics, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to a temperature-
excursion disposition: executor dispositions product that experienced a cold-
chain temperature excursion (stability impact, disposition, excursion scope);
reviewer (cross-model per ARIS §2.1) challenges an unsupported stability
conclusion, an inconsistent disposition, and an understated excursion scope, with
the power to VETO a 'release' of product whose cumulative excursion exceeds its
stability budget.

Veto gate (D-LIFESCI-4): fires when a 'release' disposition is proposed for
product whose cumulative excursion exceeds the stability budget (or has no
supporting stability data).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Temperature-monitoring / data-logger system — the excursion record should
       resolve against the controlled monitoring/logger system, not caller-pasted
       text.
    2. Stability database + mean-kinetic-temperature (MKT) budget engine — the
       stability budget should be computed by the controlled stability system.
    3. Batch / lot traceability system — the affected-units scope should resolve
       against the controlled traceability system.
    4. Deviation / disposition system — the disposition should be recorded in the
       controlled deviation-management system.
    5. Qualified approver gate — every AI-suggested disposition must be reviewed
       by qualified Quality. Output is never an auto-release; no product is
       released after an excursion by this workflow.
    6. Dedicated third-model disposition auditor — production should use a
       separately configured auditor model for stability-budget bias detection.
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
    "ADVISORY ONLY — This AI-generated cold-chain excursion disposition is "
    "decision-support, not a product-disposition decision. A qualified Quality "
    "approver must independently confirm the stability impact, excursion scope, "
    "and disposition before any product is released, quarantined, or rejected "
    "after an excursion. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "'release' disposition proposed for product whose cumulative excursion "
    "exceeds its stability budget. See metadata['veto_reason']. Escalate to "
    "Quality; the affected product must not be released until the stability "
    "impact is resolved."
)

_FLAG_HEADERS = (
    "STABILITY-IMPACT FLAGS:",
    "DISPOSITION FLAGS:",
    "EXCURSION-SCOPE FLAGS:",
)

_COLDCHAIN_REVIEW_CRITERIA = """\
Evaluate this cold-chain excursion disposition on five dimensions. Score each 0–10.

1. STABILITY-DATA JUSTIFICATION (30%) — CRITICAL
   Is the excursion's impact on potency/stability supported by stability data and
   the mean-kinetic-temperature (MKT) budget? Penalise an impact conclusion not
   supported by data. Flag under STABILITY-IMPACT FLAGS:.

2. DISPOSITION CONSISTENCY (25%) — CRITICAL
   Is the proposed disposition consistent with the stability-budget conclusion?
   Penalise a disposition that contradicts the stability finding. Flag under
   DISPOSITION FLAGS:.

3. EXCURSION-SCOPE COMPLETENESS (20%) — CRITICAL
   Is the affected-units scope and the cumulative excursion fully traced? Penalise
   an understated scope or an unsummed cumulative excursion. Flag under
   EXCURSION-SCOPE FLAGS:.

4. MKT / BUDGET RIGOR (15%)
   Is the cumulative excursion accounted for against the remaining stability
   budget with sound MKT reasoning? Penalise weak budget accounting.

5. ACTIONABILITY (10%)
   Is the disposition specific enough to act on (which lots, which budget, which
   disposition)? Penalise vague dispositions.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a 'release' disposition is proposed for product whose cumulative
excursion exceeds the stability budget (or has no supporting stability data).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero STABILITY-IMPACT FLAGS AND zero DISPOSITION FLAGS AND zero
EXCURSION-SCOPE FLAGS AND no VETO: ready for Quality sign-off. Otherwise: requires
revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  STABILITY-IMPACT FLAGS: [bullet list, or "None detected"]
  DISPOSITION FLAGS: [bullet list, or "None detected"]
  EXCURSION-SCOPE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are producing a cold-chain excursion disposition for a qualified Quality
approver. You have no stake in the outcome. Judge the excursion's stability
impact, trace the affected-units scope, and recommend a disposition — grounded
only in the data supplied.

BASE THE DISPOSITION ON THE INPUT DATA ONLY.

EXCURSION DATA:
{request_text}

{wiki_context}

Produce a structured disposition with exactly these sections:

## Excursion summary
Summarise the excursion (temperature, duration, where in the chain) and the
labeled storage condition.

## Stability impact
State the impact on potency/stability against the stability data and the MKT
budget. Do not assert acceptability the data do not support.

## Excursion scope
Trace the affected lots/units and the cumulative time-out-of-range across legs.

## Disposition
State the recommended disposition (release / quarantine / reject) consistent with
the stability-budget conclusion.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this cold-chain excursion disposition. Address EVERY issue in the
reviewer's critique, especially any STABILITY-IMPACT FLAGS, DISPOSITION FLAGS, or
EXCURSION-SCOPE FLAGS.

PREVIOUS DISPOSITION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any STABILITY-IMPACT flag: ground the impact in stability data and the MKT budget.
⚠️  For any DISPOSITION flag: align the disposition with the stability conclusion.
⚠️  For any EXCURSION-SCOPE flag: sum the cumulative excursion across all legs and lots.
"""


@dataclass
class ColdChainExcursionRequest:
    """Structured input for the cold-chain excursion disposition workflow."""

    product_description: str
    """Generic temperature-sensitive product category and labeled storage condition."""

    excursion_description: str
    """Temperature, duration, and where in the chain the excursion occurred."""

    label_storage_condition: str
    """The approved labeled storage range."""

    stability_budget_summary: str
    """Stability data / MKT budget and the allowable excursion time."""

    excursion_extent: str
    """Cumulative time-out-of-range vs the remaining budget."""

    affected_units: str
    """Lots / quantities affected and the traced scope."""

    impact_on_quality: str
    """Caller's assessment of potency / stability impact."""

    proposed_disposition: str
    """Caller's proposed disposition (release / quarantine / reject)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Excursion description: {self.excursion_description[:cap]}",
            f"Label storage condition: {self.label_storage_condition[:cap]}",
            f"Stability budget summary: {self.stability_budget_summary[:cap]}",
            f"Excursion extent: {self.excursion_extent[:cap]}",
            f"Affected units: {self.affected_units[:cap]}",
            f"Impact on quality: {self.impact_on_quality[:cap]}",
            f"Proposed disposition: {self.proposed_disposition[:cap]}",
        ])


class ColdChainExcursionWorkflow(BaseWorkflow):
    """
    Adversarial cold-chain excursion disposition: executor judges stability
    impact, traces excursion scope, and recommends a disposition → reviewer
    challenges an unsupported stability conclusion, an inconsistent disposition,
    and an understated scope, with the power to VETO → iterate.

    Convergence gate (D-LIFESCI-4):
        score ≥ threshold (8.0)
        AND zero STABILITY-IMPACT FLAGS
        AND zero DISPOSITION FLAGS
        AND zero EXCURSION-SCOPE FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: ColdChainExcursionRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_stability_flags: list[str] = []
        current_disposition_flags: list[str] = []
        current_scope_flags: list[str] = []
        all_stability_flags: list[str] = []
        all_disposition_flags: list[str] = []
        all_scope_flags: list[str] = []
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
                flag_section = self._format_flag_section(
                    current_stability_flags,
                    current_disposition_flags,
                    current_scope_flags,
                )
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
                criteria=_COLDCHAIN_REVIEW_CRITERIA,
            )
            score = review.score
            current_stability_flags = extract_flags(
                review.critique, "STABILITY-IMPACT FLAGS:"
            )
            current_disposition_flags = extract_flags(
                review.critique, "DISPOSITION FLAGS:"
            )
            current_scope_flags = extract_flags(
                review.critique, "EXCURSION-SCOPE FLAGS:"
            )
            all_stability_flags.extend(current_stability_flags)
            all_disposition_flags.extend(current_disposition_flags)
            all_scope_flags.extend(current_scope_flags)

            # Audit-trail write happens BEFORE the veto check (D-LIFESCI-4).
            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            veto_reason = self._extract_veto(review.critique, max_wiki_chars)
            if veto_reason is not None:
                break

            if (
                review.approved
                and not current_stability_flags
                and not current_disposition_flags
                and not current_scope_flags
            ):
                converged = True
                break

        coldchain_checklist = self._build_coldchain_checklist(
            request,
            {
                "STABILITY-IMPACT FLAGS:": all_stability_flags,
                "DISPOSITION FLAGS:": all_disposition_flags,
                "EXCURSION-SCOPE FLAGS:": all_scope_flags,
            },
            veto_reason,
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "stability_impact_flags": list(dict.fromkeys(all_stability_flags)),
            "disposition_flags": list(dict.fromkeys(all_disposition_flags)),
            "excursion_scope_flags": list(dict.fromkeys(all_scope_flags)),
            "coldchain_checklist": coldchain_checklist,
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
    def _format_flag_section(
        stability_flags: list[str],
        disposition_flags: list[str],
        scope_flags: list[str],
    ) -> str:
        if not stability_flags and not disposition_flags and not scope_flags:
            return ""
        parts: list[str] = []
        if stability_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(stability_flags)
            )
            parts.append(
                "⚠️  STABILITY-IMPACT FLAGS (ground the impact in stability data and "
                "the MKT budget):\n"
                f"{flags_text}"
            )
        if disposition_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(disposition_flags)
            )
            parts.append(
                "⚠️  DISPOSITION FLAGS (align the disposition with the stability "
                "conclusion):\n"
                f"{flags_text}"
            )
        if scope_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(scope_flags)
            )
            parts.append(
                "⚠️  EXCURSION-SCOPE FLAGS (sum the cumulative excursion across all "
                "legs and lots):\n"
                f"{flags_text}"
            )
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
    def _build_coldchain_checklist(
        request: ColdChainExcursionRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Quality / Cold-Chain Disposition]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — a 'release' disposition is proposed for "
                "product whose cumulative excursion exceeds its stability budget; "
                "escalate to Quality and do not release until the impact is resolved"
            )
        stability_flags = accumulated.get("STABILITY-IMPACT FLAGS:", [])
        disposition_flags = accumulated.get("DISPOSITION FLAGS:", [])
        scope_flags = accumulated.get("EXCURSION-SCOPE FLAGS:", [])
        if stability_flags:
            checklist.append(
                f"[ ] ⚠️  STABILITY-IMPACT FLAGS ({len(stability_flags)}) — ground "
                "each impact conclusion in stability data and the MKT budget"
            )
        if disposition_flags:
            checklist.append(
                f"[ ] ⚠️  DISPOSITION FLAGS ({len(disposition_flags)}) — align the "
                "disposition with the stability conclusion"
            )
        if scope_flags:
            checklist.append(
                f"[ ] ⚠️  EXCURSION-SCOPE FLAGS ({len(scope_flags)}) — sum the "
                "cumulative excursion across every leg and affected lot"
            )
        checklist.extend([
            "[ ] Ground the stability impact in the MKT budget and stability data",
            "[ ] Confirm the disposition is consistent with the stability conclusion",
            "[ ] Trace every affected lot and sum the cumulative excursion",
            "[ ] Obtain Quality sign-off before any post-excursion release",
        ])
        return checklist
