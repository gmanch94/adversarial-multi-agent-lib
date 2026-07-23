"""
Workflow — Engineering Change Order (Industrial Manufacturing Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to ECO impact
assessment: when a design change is proposed, what does it break in the
field, in adjacent products, in supplier tooling, and in service-parts
compatibility?

Executor drafts an ECO impact assessment; reviewer (recommended:
different model family per ARIS §2.1 principle 1) challenges supersession
mapping (which form/fit/function variants are valid replacements),
FMEA-delta completeness, and regression risk for deployed product.

Triple-flag gate (D-IND-1): SUPERSESSION FLAGS, FMEA-DELTA FLAGS,
REGRESSION FLAGS. **No reviewer veto** — ECOs are reversible via
rollback ECO; the gate is impact-discipline, not life-safety halt.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PLM integration (Teamcenter / Windchill / Aras) — BOM diff,
       supersession rules, and effectivity must come from structured PLM
       records, not paraphrased CAD-system change notes.
    2. PFMEA / DFMEA linkage — every design change must update the FMEA
       with new failure-mode-effect-cause-control-detection rows; not done
       here.
    3. Service-parts catalog — service-bulletin generation, parts catalog
       update, and retrofit instructions belong in a structured service
       system, not narrative.
    4. Supplier tooling impact — supplier PPAP / tooling amortisation
       impact belongs in the structured PPAP workflow, not analyst summary.
    5. CAB / ECR / ECN workflow — change-advisory-board approval,
       engineering-change-request initiation, and engineering-change-notice
       release belong in a structured ECN system.
    6. Regression test plan — verification matrix and field-test plan
       require structured test management, not prose.
    7. Append-only audit store + dedicated third-model auditor — see
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
    "⚠️  ADVISORY ONLY — This AI-generated ECO impact assessment is not "
    "an authorised engineering-change release. A credentialed change "
    "control board / change-advisory-board member must verify "
    "supersession rules, FMEA delta, and regression scope before any ECN "
    "is released. AI output must never trigger an automated ECN release."
)

_ECO_REVIEW_CRITERIA = """\
Evaluate this ECO impact assessment on four dimensions. Score each 0–10.

1. SUPERSESSION RIGOUR (30%) — CRITICAL
   Is form / fit / function compatibility analysed for each affected part
   number? Are supersession rules stated (interchangeable in both
   directions / interchangeable one-way / not interchangeable)? Is the
   effectivity (date-effective vs serial-effective vs lot-effective)
   credible? Penalise wave-of-the-hand "drop-in replacement" claims with
   no F/F/F evidence. Flag every gap under SUPERSESSION FLAGS:.

2. FMEA-DELTA COMPLETENESS (30%) — CRITICAL
   Does the assessment update PFMEA / DFMEA rows for new failure modes
   introduced or eliminated? Are severity / occurrence / detection ratings
   re-evaluated with evidence? Is the risk-priority-number delta stated?
   Penalise design changes with no FMEA update. Flag every gap under
   FMEA-DELTA FLAGS:.

3. REGRESSION RISK (25%) — CRITICAL
   Does the assessment identify deployed-product compatibility risk
   (firmware mismatch, service-parts back-compat, harness-pinout change,
   adjacent-product reuse of the same component)? Is the regression test
   plan adequate (verification + validation + field-trial)? Penalise
   narrowly-scoped regression that ignores field-installed product.
   Flag every gap under REGRESSION FLAGS:.

4. ACTIONABILITY (15%)
   Are the next actions (supplier notice, PPAP re-run, service-bulletin,
   parts-catalog update, retrofit-program decision, CAB approval) specific
   enough for the change board to execute?

Overall score = weighted average.
Score ≥ 7.5 AND zero SUPERSESSION FLAGS AND zero FMEA-DELTA FLAGS AND
zero REGRESSION FLAGS: assessment is ready for change-advisory-board
review. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SUPERSESSION FLAGS: [bullet list, or "None detected"]
  FMEA-DELTA FLAGS: [bullet list, or "None detected"]
  REGRESSION FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing an ECO impact assessment for an industrial OEM's
change-advisory-board. You have no stake in the outcome. Your job is to
identify every downstream impact of the proposed design change — not to
expedite the change, not to inflate the impact for cautious defaults.

BASE THE ASSESSMENT ON THE INPUT DATA.

ECO DATA:
{request_text}

{wiki_context}

Produce a structured assessment with exactly these sections:

## Change Summary
Restate the proposed change: BOM diff, drawing revisions, reason for
change (cost / quality / obsolescence / regulatory / safety), effectivity
proposal.

## Supersession Rules
For each affected part number: form / fit / function analysis,
supersession direction (one-way / two-way / not interchangeable),
effectivity basis.

## FMEA Delta
PFMEA / DFMEA rows added, modified, or eliminated. Severity / occurrence
/ detection delta. New or eliminated failure modes.

## Regression Risk
Deployed-product impact: firmware-compatibility, service-parts back-compat,
adjacent-product reuse of same component, harness or pinout change.
Verification + validation + field-trial plan.

## Supplier and Tooling Impact
Supplier notice required, PPAP re-run scope, tooling amortisation
impact, lead-time for first valid replacement.

## Service and Aftermarket
Service-bulletin required, parts-catalog update, retrofit decision
(mandatory / optional / on-failure), repair-procedure update.

## CAB Recommendation
Approve / Approve with conditions / Reject / Defer. State the conditions
and the approving authority.

## Evidence Gaps
Information missing from the inputs that materially affects the
assessment.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this ECO impact assessment. Address EVERY issue in the reviewer's
critique, especially any SUPERSESSION FLAGS, FMEA-DELTA FLAGS, or
REGRESSION FLAGS.

PREVIOUS ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SUPERSESSION FLAG: re-state F/F/F analysis with evidence;
update the supersession direction or downgrade to "not interchangeable".
⚠️  For any FMEA-DELTA FLAG: add the missing PFMEA / DFMEA row with
S/O/D values and RPN delta.
⚠️  For any REGRESSION FLAG: expand the verification scope or add a
field-trial step; address the deployed-product compatibility risk.
"""


@dataclass
class EngineeringChangeOrderRequest:
    """Structured input for the ECO impact assessment workflow."""

    change_summary: str
    """BOM diff, drawing revisions, reason for change, proposed effectivity."""

    affected_part_numbers: str
    """Part numbers affected with current revision, proposed revision,
    sub-assembly / next-assembly references."""

    f3_analysis: str
    """Form / fit / function analysis as drafted by the originator."""

    fmea_context: str
    """Current PFMEA / DFMEA rows for affected components; proposed
    delta / additions."""

    deployed_product_context: str
    """Field-installed product population, firmware versions in use,
    service-parts catalog state, adjacent-product reuse."""

    supplier_and_tooling_context: str
    """Supplier impact (PPAP re-run, tooling amortisation), lead-time,
    capacity reservation."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Change summary: {self.change_summary[:cap]}",
            f"Affected part numbers: {self.affected_part_numbers[:cap]}",
            f"F/F/F analysis: {self.f3_analysis[:cap]}",
            f"FMEA context: {self.fmea_context[:cap]}",
            f"Deployed product context: {self.deployed_product_context[:cap]}",
            f"Supplier and tooling context: {self.supplier_and_tooling_context[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "SUPERSESSION FLAGS:",
    "FMEA-DELTA FLAGS:",
    "REGRESSION FLAGS:",
)


class EngineeringChangeOrderWorkflow(BaseWorkflow):
    """
    Adversarial ECO impact review: executor drafts an impact assessment →
    reviewer challenges supersession rigour, FMEA-delta completeness, and
    regression coverage → iterate.

    Convergence gate (D-IND-1):
        score ≥ threshold
        AND zero SUPERSESSION FLAGS
        AND zero FMEA-DELTA FLAGS
        AND zero REGRESSION FLAGS

    No reviewer veto — ECOs are reversible via rollback ECO.
    """

    async def run(  # type: ignore[override]
        self,
        request: EngineeringChangeOrderRequest,
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
                criteria=_ECO_REVIEW_CRITERIA,
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

            if review.approved and not any(current.values()):
                converged = True
                break

        approver_checklist = self._build_approver_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "change_summary": sanitize_for_prompt(
                    request.change_summary, max_chars=200
                ),
                "supersession_flags": list(
                    dict.fromkeys(accumulated["SUPERSESSION FLAGS:"])
                ),
                "fmea_delta_flags": list(
                    dict.fromkeys(accumulated["FMEA-DELTA FLAGS:"])
                ),
                "regression_flags": list(
                    dict.fromkeys(accumulated["REGRESSION FLAGS:"])
                ),
                "approver_checklist": approver_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "SUPERSESSION FLAGS:": (
                "⚠️  SUPERSESSION FLAGS (re-state F/F/F with evidence or "
                "downgrade to not-interchangeable):"
            ),
            "FMEA-DELTA FLAGS:": (
                "⚠️  FMEA-DELTA FLAGS (add missing PFMEA / DFMEA rows with "
                "S/O/D values and RPN delta):"
            ),
            "REGRESSION FLAGS:": (
                "⚠️  REGRESSION FLAGS (expand verification scope or add "
                "field-trial step; address deployed-product compatibility):"
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
    def _build_approver_checklist(
        request: EngineeringChangeOrderRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["SUPERSESSION FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  SUPERSESSION FLAGS "
                f"({len(accumulated['SUPERSESSION FLAGS:'])}) — "
                "re-state F/F/F with PLM evidence before ECN release"
            )
        if accumulated["FMEA-DELTA FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  FMEA-DELTA FLAGS "
                f"({len(accumulated['FMEA-DELTA FLAGS:'])}) — "
                "update PFMEA / DFMEA with S/O/D and RPN delta"
            )
        if accumulated["REGRESSION FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  REGRESSION FLAGS "
                f"({len(accumulated['REGRESSION FLAGS:'])}) — "
                "expand verification + add field-trial for deployed product"
            )
        checklist.extend([
            "[ ] Change-advisory-board approval per ECN authority matrix",
            "[ ] PLM commit: BOM diff + supersession rules + effectivity",
            "[ ] Supplier-notice issued; PPAP re-run for affected parts",
            "[ ] Service-bulletin drafted; parts-catalog updated",
            "[ ] Retrofit decision (mandatory / optional / on-failure) documented",
            f"[ ] Affected serials reviewed: {request.deployed_product_context[:60]}",
            "[ ] Release ECN — AI output must not trigger automatic release",
        ])
        return checklist
