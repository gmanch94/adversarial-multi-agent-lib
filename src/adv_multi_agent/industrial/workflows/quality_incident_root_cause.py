"""
Workflow — Quality Incident Root-Cause (Industrial Manufacturing Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to 8D / DMAIC
root-cause investigation for a quality incident (in-plant escape, field
failure, customer complaint).

Executor drafts a root-cause analysis; reviewer (recommended: different
model family per ARIS §2.1 principle 1) challenges shallow causal chains,
incomplete containment, and missed systemic implications. The reviewer
specifically pushes back on convenient "operator error" attribution that
may mask design-defect or process-control signal.

Triple-flag gate (D-IND-1): CAUSAL-CHAIN FLAGS, CONTAINMENT FLAGS,
SYSTEMIC FLAGS. **No reviewer veto** — quality findings are reversible
through corrective-action review. Escalation to product-liability /
recall workflows is handled by downstream workflows (#8, #9).

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. MES / QMS integration — non-conformance records, in-process SPC
       data, and serial-number traceability must come from a structured
       quality system, not paraphrased prose.
    2. FRACAS / CMMS feed — field-failure mode evidence belongs in a
       structured failure-reporting database with mode-effect linkage.
    3. DOE / SPC engine — root-cause hypotheses should be tested against
       structured process data with statistical rigor, not narrative.
    4. PFMEA linkage — every confirmed cause must update the PFMEA risk
       priority number; not done here.
    5. CAPA workflow integration — corrective-action / preventive-action
       tracking belongs in a structured CAPA system tied to ECO release.
    6. Append-only audit store + dedicated third-model auditor — see
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
    "⚠️  ADVISORY ONLY — This AI-generated root-cause analysis is not an "
    "authorised CAPA or PFMEA update. A credentialed quality engineer "
    "must verify the causal chain against measurement-system evidence "
    "before any corrective action is released or PFMEA risk-priority "
    "number is changed. AI output must never trigger an automated CAPA "
    "release."
)

_QUALITY_REVIEW_CRITERIA = """\
Evaluate this root-cause analysis on four dimensions. Score each 0–10.

1. CAUSAL-CHAIN RIGOUR (35%) — CRITICAL
   Is the 5-Why / fishbone causal chain anchored on objective evidence
   (SPC data, measurement-system results, serial-number trace, failed-
   part teardown)? Does the chain reach a true root cause, not stop at a
   convenient proximal cause? Penalise "operator error" attribution that
   masks a design or process-control gap. Flag every weak link under
   CAUSAL-CHAIN FLAGS:.

2. CONTAINMENT COMPLETENESS (30%) — CRITICAL
   Does the containment cover all serial numbers / batches at risk
   (in-plant WIP + finished goods + in-transit + customer-held +
   field-deployed)? Is the sort method credible (100% inspection / Cpk-
   bounded sample / measurement-system capable)? Penalise containment
   scoped only to the failing unit. Flag every gap under CONTAINMENT FLAGS:.

3. SYSTEMIC IMPLICATIONS (25%) — CRITICAL
   Could this failure mode exist on adjacent products / platforms / shared
   tooling / shared supplier? Has the PFMEA RPN been re-evaluated? Are
   read-across actions for sister parts proposed? Penalise narrow
   problem-statement scoping. Flag every miss under SYSTEMIC FLAGS:.

4. ACTIONABILITY (10%)
   Are corrective and preventive actions specific (owner, due date,
   measurable success criterion)? Is the CAPA tied to an ECO if a design
   change is required?

Overall score = weighted average.
Score ≥ 7.5 AND zero CAUSAL-CHAIN FLAGS AND zero CONTAINMENT FLAGS AND
zero SYSTEMIC FLAGS: analysis is ready for quality-engineering review.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  CAUSAL-CHAIN FLAGS: [bullet list, or "None detected"]
  CONTAINMENT FLAGS: [bullet list, or "None detected"]
  SYSTEMIC FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a root-cause analysis for an industrial OEM's quality
engineering review. You have no stake in the outcome. Your job is to
trace the failure to its true root cause with evidence — not to land on
the most convenient explanation, not to stop at the operator if the
process control is missing.

BASE THE ANALYSIS ON THE INPUT DATA.

INCIDENT DATA:
{request_text}

{wiki_context}

Produce a structured analysis with exactly these sections:

## Incident Summary
Restate the incident: date, product, serial / batch, failure mode, severity,
how it was detected, where it was detected.

## Evidence Inventory
List all available evidence: SPC data, measurement-system results, failed-
part teardown findings, witness statements, traceability records. Note
gaps explicitly.

## Causal Chain (5-Why or Equivalent)
Build the causal chain from failure mode to root cause. Cite the evidence
supporting each link. Do not stop at "operator error" unless the process
provides operator-proof control AND that control was tested.

## Containment
State containment scope: in-plant WIP + finished goods + in-transit +
customer-held + field-deployed. State the sort method and its measurement-
system capability.

## Systemic Read-Across
Identify adjacent products / platforms / shared tooling / shared supplier
that may share the failure mode. Propose read-across actions.

## Corrective and Preventive Actions
For each confirmed cause: corrective action (owner, due, success criterion)
and preventive action. Tie to ECO if design change required.

## Evidence Gaps
Information missing from the inputs that materially affects root-cause
attribution.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this root-cause analysis. Address EVERY issue in the reviewer's
critique, especially any CAUSAL-CHAIN FLAGS, CONTAINMENT FLAGS, or
SYSTEMIC FLAGS.

PREVIOUS ANALYSIS:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any CAUSAL-CHAIN FLAG: deepen the 5-Why with cited evidence;
remove unsupported "operator error" attribution unless operator-proof
control existed.
⚠️  For any CONTAINMENT FLAG: expand containment scope or upgrade sort
method; cite measurement-system capability.
⚠️  For any SYSTEMIC FLAG: enumerate sister parts / platforms / tooling
shared with the failure mode and propose read-across.
"""


@dataclass
class QualityIncidentRootCauseRequest:
    """Structured input for the quality-incident root-cause workflow."""

    incident_summary: str
    """Date, product, serial/batch, failure mode, severity, detection point."""

    evidence_inventory: str
    """Available SPC data, measurement-system results, teardown findings,
    witness statements, traceability."""

    initial_causal_hypothesis: str
    """Investigator's first-pass root-cause hypothesis + supporting reasoning."""

    containment_scope: str
    """Current containment scope: WIP / finished / in-transit / customer-held /
    field-deployed + sort method."""

    process_and_design_context: str
    """Relevant PFMEA entries, SPC baseline, recent ECOs, supplier-related
    changes."""

    adjacent_products: str
    """Products / platforms / shared tooling / shared supplier that may share
    the failure mode."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Incident summary: {self.incident_summary[:cap]}",
            f"Evidence inventory: {self.evidence_inventory[:cap]}",
            f"Initial causal hypothesis: {self.initial_causal_hypothesis[:cap]}",
            f"Containment scope: {self.containment_scope[:cap]}",
            f"Process and design context: {self.process_and_design_context[:cap]}",
            f"Adjacent products: {self.adjacent_products[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "CAUSAL-CHAIN FLAGS:",
    "CONTAINMENT FLAGS:",
    "SYSTEMIC FLAGS:",
)


class QualityIncidentRootCauseWorkflow(BaseWorkflow):
    """
    Adversarial root-cause analysis: executor drafts 5-Why + containment +
    read-across → reviewer challenges shallow chains, narrow containment,
    and missed systemic implications → iterate.

    Convergence gate (D-IND-1):
        score ≥ threshold
        AND zero CAUSAL-CHAIN FLAGS
        AND zero CONTAINMENT FLAGS
        AND zero SYSTEMIC FLAGS

    No reviewer veto. Escalation to product-liability / recall workflows
    is handled downstream.
    """

    async def run(  # type: ignore[override]
        self,
        request: QualityIncidentRootCauseRequest,
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
                criteria=_QUALITY_REVIEW_CRITERIA,
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
                "incident_summary": request.incident_summary,
                "causal_chain_flags": list(
                    dict.fromkeys(accumulated["CAUSAL-CHAIN FLAGS:"])
                ),
                "containment_flags": list(
                    dict.fromkeys(accumulated["CONTAINMENT FLAGS:"])
                ),
                "systemic_flags": list(dict.fromkeys(accumulated["SYSTEMIC FLAGS:"])),
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
            "CAUSAL-CHAIN FLAGS:": (
                "⚠️  CAUSAL-CHAIN FLAGS (deepen the 5-Why with cited evidence; "
                "remove unsupported operator-error attribution):"
            ),
            "CONTAINMENT FLAGS:": (
                "⚠️  CONTAINMENT FLAGS (expand scope or upgrade sort method; "
                "cite measurement-system capability):"
            ),
            "SYSTEMIC FLAGS:": (
                "⚠️  SYSTEMIC FLAGS (enumerate sister parts / platforms / "
                "shared tooling and propose read-across):"
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
        request: QualityIncidentRootCauseRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["CAUSAL-CHAIN FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  CAUSAL-CHAIN FLAGS "
                f"({len(accumulated['CAUSAL-CHAIN FLAGS:'])}) — "
                "deepen 5-Why with measurement-system evidence before CAPA release"
            )
        if accumulated["CONTAINMENT FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  CONTAINMENT FLAGS "
                f"({len(accumulated['CONTAINMENT FLAGS:'])}) — "
                "expand containment scope; verify sort-method capability"
            )
        if accumulated["SYSTEMIC FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  SYSTEMIC FLAGS ({len(accumulated['SYSTEMIC FLAGS:'])}) — "
                "issue read-across notices to adjacent product / platform owners"
            )
        checklist.extend([
            "[ ] Quality engineering sign-off on causal chain + measurement evidence",
            "[ ] PFMEA risk-priority-number update for confirmed cause",
            "[ ] CAPA opened with owner, due-date, success criterion",
            "[ ] ECO opened if design change required (see EngineeringChangeOrderWorkflow)",
            "[ ] Escalate to ProductLiabilityRootCauseWorkflow if injury / property-damage exposure",
            f"[ ] Confirm adjacent-product list reviewed: {request.adjacent_products[:60]}",
            "[ ] Release CAPA — AI output must not trigger automatic action",
        ])
        return checklist
