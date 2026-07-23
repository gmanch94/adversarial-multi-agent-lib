"""
Workflow — Field-Action Classification / Recall-Class Determination
(Lifesciences · Devices post-market, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to medical-device
field-action classification: executor proposes a recall class, a 21 CFR 806
correction-vs-removal reportability call, a health-hazard evaluation, and the
affected-lot / distribution scope for a field action; reviewer (cross-model per
ARIS §2.1) challenges any recall-class downgrade, any 'not reportable'
mischaracterisation, and any understated hazard, with the power to VETO when a
downgrade or non-reportable call would leave patients exposed.

BOUNDARY (D-LIFESCI-2): distinct from the industrial RecallScopeManufacturingWorkflow — that scopes a general product recall; this assigns an FDA medical-device recall class (I/II/III) and the 21 CFR 806 correction-vs-removal reportability call.

Veto gate (D-LIFESCI-3): fires when a recall-class downgrade or a 'not reportable'
call would leave patients exposed to a hazard that the correct class /
reportability would address.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Complaint / CAPA system — the problem, root cause, and prior actions
       should resolve against the controlled complaint-handling / CAPA QMS, not
       caller-pasted narrative text.
    2. FDA Recall Enterprise System — a determined recall must be filed through
       the FDA Recall Enterprise System (RES); this workflow does not file.
    3. Health-hazard-evaluation board — the health-hazard evaluation should be
       ratified by the controlled health-hazard-evaluation board, not produced
       by a single model pass.
    4. UDI / lot-genealogy traceability — affected lots / serials and
       distribution scope should reconcile against the UDI / lot-genealogy
       traceability system, not caller-supplied free text.
    5. Dedicated third-model hazard auditor — production should use a separately
       configured auditor model for recall-class / hazard-probability review.
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
    "ADVISORY ONLY — This AI-generated field-action classification is "
    "decision-support, not an FDA recall determination. A qualified Recall "
    "committee / Chief Quality Officer must independently confirm the recall "
    "class, health-hazard evaluation, and 21 CFR 806 reportability before any "
    "field action. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "recall-class downgrade or 'not reportable' call that leaves patients "
    "exposed. See metadata['veto_reason']. Escalate to the Recall committee / "
    "CQO; do not under-scope the action."
)

_FLAG_HEADERS = ("RECALL-CLASS FLAGS:", "CORRECTION-REMOVAL FLAGS:", "HEALTH-HAZARD FLAGS:")

_FIELD_ACTION_REVIEW_CRITERIA = """\
Evaluate this field-action classification on five dimensions. Score each 0–10.

1. RECALL CLASSIFICATION (30%) — CRITICAL
   Is the proposed recall class consistent with the health hazard? Penalise a
   Class II proposed where a reasonable probability of serious adverse health
   consequences indicates Class I. Flag under RECALL-CLASS FLAGS:.

2. CORRECTION-REMOVAL REPORTABILITY (25%) — CRITICAL
   Is a 21 CFR 806 reportable correction/removal correctly characterised, and
   not mislabelled as a non-reportable enhancement or routine stock recovery?
   Penalise a reportable action characterised as non-reportable. Flag under
   CORRECTION-REMOVAL FLAGS:.

3. HEALTH-HAZARD EVALUATION (20%) — CRITICAL
   Does the health-hazard evaluation state probability, severity, and affected
   population without understating any? Penalise an evaluation that understates
   the hazard. Flag under HEALTH-HAZARD FLAGS:.

4. SCOPE COMPLETENESS (15%)
   Are affected lots/serials and distribution scope complete for the root cause?
   Penalise an under-scoped lot/distribution list.

5. ACTIONABILITY (10%)
   Is the classification specific enough to act on (class, reportability call,
   scope)? Penalise vague classification.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a recall-class downgrade or a 'not reportable' call would leave
patients exposed to a hazard that the correct class/reportability would address.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero RECALL-CLASS FLAGS AND zero CORRECTION-REMOVAL FLAGS AND
zero HEALTH-HAZARD FLAGS AND no VETO: ready for Recall committee sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  RECALL-CLASS FLAGS: [bullet list, or "None detected"]
  CORRECTION-REMOVAL FLAGS: [bullet list, or "None detected"]
  HEALTH-HAZARD FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are producing a medical-device field-action classification for a qualified
Recall committee / Chief Quality Officer. You have no stake in the outcome.
Your job is to assign a recall class consistent with the health hazard, make the
21 CFR 806 correction-vs-removal reportability call, state a health-hazard
evaluation, and scope the affected lots / distribution — grounded only in the
data supplied.

BASE THE CLASSIFICATION ON THE INPUT DATA ONLY.

FIELD-ACTION DATA:
{request_text}

{wiki_context}

Produce a structured field-action classification with exactly these sections:

## Problem and root cause
Summarise the problem and the root cause from the input.

## Health-hazard evaluation
State probability, severity, and affected population. Do not understate any.

## Recall classification
Assign the recall class (I/II/III) and justify it against the health hazard. Do
not downgrade a Class I hazard to a lower class.

## Correction vs removal reportability
Apply the 21 CFR 806 reportability test. State whether the action is a reportable
correction or removal, and do not mislabel a reportable action as a
non-reportable enhancement or routine stock recovery.

## Scope (lots / distribution)
State the affected lots/serials and distribution scope, complete for the root
cause.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this field-action classification. Address EVERY issue in the reviewer's
critique, especially any RECALL-CLASS FLAGS, CORRECTION-REMOVAL FLAGS, or
HEALTH-HAZARD FLAGS.

PREVIOUS CLASSIFICATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any RECALL-CLASS flag: re-derive the class from the health hazard.
⚠️  For any CORRECTION-REMOVAL flag: apply the 21 CFR 806 reportability test.
⚠️  For any HEALTH-HAZARD flag: re-state probability/severity/population without
understating.
"""


@dataclass
class FieldActionRequest:
    """Structured input for the field-action classification workflow."""

    problem_description: str
    """The problem: what is defective and how it can affect the device's use."""

    health_hazard_evaluation: str
    """The health-hazard evaluation: probability, severity, affected population."""

    affected_lots_serials: str
    """The affected lots / serials for the field action."""

    distribution_scope: str
    """Where the affected product was distributed."""

    action_type: str
    """The proposed field action (correction, removal, stock recovery, etc.)."""

    root_cause_summary: str
    """The root cause of the defect."""

    patient_exposure_estimate: str
    """Estimated number of patients / devices exposed."""

    prior_related_actions: str
    """Any prior related field actions on this product line."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Problem description: {self.problem_description[:cap]}",
            f"Health-hazard evaluation: {self.health_hazard_evaluation[:cap]}",
            f"Affected lots/serials: {self.affected_lots_serials[:cap]}",
            f"Distribution scope: {self.distribution_scope[:cap]}",
            f"Action type: {self.action_type[:cap]}",
            f"Root cause summary: {self.root_cause_summary[:cap]}",
            f"Patient exposure estimate: {self.patient_exposure_estimate[:cap]}",
            f"Prior related actions: {self.prior_related_actions[:cap]}",
        ])


class FieldActionClassificationWorkflow(BaseWorkflow):
    """
    Adversarial field-action classification: executor assigns a recall class,
    the 21 CFR 806 reportability call, and the health-hazard evaluation →
    reviewer challenges recall-class downgrades, non-reportable mischaracter-
    isations, and understated hazards, with the power to VETO → iterate.

    BOUNDARY (D-LIFESCI-2): distinct from the industrial
    RecallScopeManufacturingWorkflow — that scopes a general product recall;
    this assigns an FDA medical-device recall class (I/II/III) and the 21 CFR
    806 correction-vs-removal reportability call.

    Convergence gate (D-LIFESCI-3):
        score ≥ threshold (8.0)
        AND zero RECALL-CLASS FLAGS
        AND zero CORRECTION-REMOVAL FLAGS
        AND zero HEALTH-HAZARD FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: FieldActionRequest,
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
                criteria=_FIELD_ACTION_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            # Audit-trail writes happen BEFORE the veto check — preserves the
            # round-N draft in wiki + ledger even if vetoed (D-LIFESCI-3).
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

        field_action_checklist = self._build_field_action_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "action_type": sanitize_for_prompt(request.action_type, max_chars=200),
            "recall_class_flags": list(
                dict.fromkeys(accumulated["RECALL-CLASS FLAGS:"])
            ),
            "correction_removal_flags": list(
                dict.fromkeys(accumulated["CORRECTION-REMOVAL FLAGS:"])
            ),
            "health_hazard_flags": list(
                dict.fromkeys(accumulated["HEALTH-HAZARD FLAGS:"])
            ),
            "field_action_checklist": field_action_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the Recall committee sees what the AI produced before the REVIEWER
            # VETO banner was prepended.
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
            "RECALL-CLASS FLAGS:": (
                "⚠️  RECALL-CLASS FLAGS (re-derive the class from the health "
                "hazard):"
            ),
            "CORRECTION-REMOVAL FLAGS:": (
                "⚠️  CORRECTION-REMOVAL FLAGS (apply the 21 CFR 806 reportability "
                "test):"
            ),
            "HEALTH-HAZARD FLAGS:": (
                "⚠️  HEALTH-HAZARD FLAGS (re-state probability/severity/population "
                "without understating):"
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
    def _build_field_action_checklist(
        request: FieldActionRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Recall Committee / Chief Quality Officer]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — a recall-class downgrade or 'not "
                "reportable' call leaves patients exposed; escalate to the Recall "
                "committee / CQO and do not under-scope the action"
            )
        recall_class_flags = accumulated.get("RECALL-CLASS FLAGS:", [])
        correction_removal_flags = accumulated.get("CORRECTION-REMOVAL FLAGS:", [])
        health_hazard_flags = accumulated.get("HEALTH-HAZARD FLAGS:", [])
        if recall_class_flags:
            checklist.append(
                f"[ ] ⚠️  RECALL-CLASS FLAGS ({len(recall_class_flags)}) — "
                "re-derive the class from the health hazard for each"
            )
        if correction_removal_flags:
            checklist.append(
                f"[ ] ⚠️  CORRECTION-REMOVAL FLAGS ({len(correction_removal_flags)}) — "
                "apply the 21 CFR 806 reportability test"
            )
        if health_hazard_flags:
            checklist.append(
                f"[ ] ⚠️  HEALTH-HAZARD FLAGS ({len(health_hazard_flags)}) — "
                "re-state probability/severity/population without understating"
            )
        checklist.extend([
            "[ ] Re-derive the recall class from the health hazard",
            "[ ] Apply the 21 CFR 806 correction-vs-removal reportability test",
            "[ ] Re-state the health-hazard evaluation (probability/severity/population)",
            "[ ] Confirm the affected lot / distribution scope is complete",
            "[ ] Obtain Recall committee sign-off before the field action proceeds",
        ])
        return checklist
