"""
Workflow — Design Control Traceability Audit (Lifesciences · Devices)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for 21 CFR 820.30 / ISO 13485
design-control traceability. Executor audits input->output->verification->
validation links; reviewer (recommended: different model family) challenges
orphan requirements, missing verification evidence, and V&V conflation.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PLM integration — design inputs/outputs should be pulled live from the
       controlled PLM system, not caller-pasted text.
    2. Requirements management — the trace matrix should resolve against the
       controlled requirements-management tool, not a manual summary.
    3. eQMS integration — verification/validation records should resolve to
       controlled eQMS records with effective dates, not draft excerpts.
    4. ISO 14971 risk-management file — hazard/risk-control linkage should be
       read from the live RMF, not a caller-supplied reference string.
    5. Qualified approver gate — every AI-suggested trace conclusion must be
       reviewed and confirmed by a qualified Design Assurance / QE engineer
       before design transfer. Output is never auto-filed to the DHF.
    6. Dedicated third-model traceability auditor — production should use a
       separately configured auditor model for orphan-link bias detection.
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

# L-PC-3: per-field cap — prevents a single oversized field crowding out
# later fields when the concatenated prompt is trimmed by sanitize_for_prompt.
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated design-control traceability audit is "
    "decision-support, not a Design History File and not a regulatory "
    "submission. A qualified Design Assurance engineer or QE must independently "
    "verify every input-output-verification-validation link against the DHF "
    "before any 21 CFR 820.30 / ISO 13485 conclusion. Not legal or medical advice."
)

_DESIGN_CONTROL_REVIEW_CRITERIA = """\
Evaluate this design-control traceability audit on five dimensions. Score each 0–10.

1. INPUT-OUTPUT TRACEABILITY (30%) — CRITICAL
   Does every design input (requirement) trace to at least one design output
   (specification), and every output trace back to an input? Penalise orphan
   inputs and orphan outputs. Flag each broken link under TRACE-GAP FLAGS:.

2. VERIFICATION EVIDENCE (25%) — CRITICAL
   Does every design output have verification evidence demonstrating the output
   meets the input? Penalise outputs asserted verified without cited evidence.
   Flag gaps under VERIFICATION FLAGS:.

3. VALIDATION EVIDENCE (20%) — CRITICAL
   Does every user need have design-validation evidence (device meets user
   needs / intended use)? Penalise V&V conflation (verification cited where
   validation is required). Flag gaps under VALIDATION FLAGS:.

4. RISK-CONTROL LINKAGE (15%)
   Are ISO 14971 risk controls traced to the verification/validation that
   confirms their effectiveness? Penalise risk controls with no confirming V&V.

5. ACTIONABILITY (10%)
   Is each gap specific enough for a QE to close (which input, which output,
   what evidence is missing)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero TRACE-GAP FLAGS AND zero VERIFICATION FLAGS AND zero
VALIDATION FLAGS: ready for Design Assurance sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  TRACE-GAP FLAGS: [bullet list, or "None detected"]
  VERIFICATION FLAGS: [bullet list, or "None detected"]
  VALIDATION FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are auditing design-control traceability for a Design Assurance engineer to
review. You have no stake in the outcome. Audit input->output->verification->
validation links against the supplied Design History File evidence — not against
general device norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert a trace link that is not
present in the design inputs, design outputs, verification, or validation
evidence below.

DESIGN HISTORY FILE EXCERPT (caller-supplied — verify against the PLM/eQMS
before acting):
{request_text}

{wiki_context}

Produce an audit with:

## Traceability matrix summary
- Input-to-output and output-to-input link status; name every orphan

## Verification coverage
- Each design output and its cited verification evidence (or the gap)

## Validation coverage
- Each user need and its cited design-validation evidence (or the gap)

## Risk-control linkage
- ISO 14971 risk controls and the V&V that confirms their effectiveness

## Gaps and recommendations
- Specific, closeable gaps (which input, which output, what evidence)

## Claims
- Specific factual claims about the DHF evidence that ground the audit
"""

_REVISION_PROMPT = """\
Revise the design-control traceability audit based on reviewer critique.

ORIGINAL AUDIT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact missing input↔output↔evidence link from
the DHF inputs; do not assert a link that is not in the supplied evidence.
"""


@dataclass
class DesignControlRequest:
    """Structured input for the design-control traceability audit workflow."""

    device_description: str
    """Generic device category, intended use, and configuration."""

    design_inputs: str
    """Design inputs / requirements (IDs + descriptions)."""

    design_outputs: str
    """Design outputs / specifications (IDs + descriptions)."""

    verification_evidence: str
    """Verification records demonstrating outputs meet inputs."""

    validation_evidence: str
    """Design-validation records demonstrating the device meets user needs."""

    risk_analysis_reference: str
    """ISO 14971 risk-management file reference and key risk controls."""

    design_review_records: str
    """Design-review records / phase-gate approvals."""

    trace_matrix_summary: str
    """Caller's summary of the input-output-V&V trace matrix."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Device description: {self.device_description[:cap]}",
            f"Design inputs: {self.design_inputs[:cap]}",
            f"Design outputs: {self.design_outputs[:cap]}",
            f"Verification evidence: {self.verification_evidence[:cap]}",
            f"Validation evidence: {self.validation_evidence[:cap]}",
            f"Risk analysis reference: {self.risk_analysis_reference[:cap]}",
            f"Design review records: {self.design_review_records[:cap]}",
            f"Trace matrix summary: {self.trace_matrix_summary[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "TRACE-GAP FLAGS:",
    "VERIFICATION FLAGS:",
    "VALIDATION FLAGS:",
)


class DesignControlTraceabilityWorkflow(BaseWorkflow):
    """
    Adversarial design-control traceability audit: executor audits
    input->output->verification->validation links → reviewer challenges orphan
    requirements, missing verification, and V&V conflation → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero TRACE-GAP FLAGS
        AND zero VERIFICATION FLAGS
        AND zero VALIDATION FLAGS

    No reviewer veto — traceability corrections are reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: DesignControlRequest,
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
                criteria=_DESIGN_CONTROL_REVIEW_CRITERIA,
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

        design_control_checklist = self._build_design_control_checklist(
            request, accumulated
        )

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "device_description": sanitize_for_prompt(
                    request.device_description, max_chars=200
                ),
                "trace_gap_flags": list(dict.fromkeys(accumulated["TRACE-GAP FLAGS:"])),
                "verification_flags": list(
                    dict.fromkeys(accumulated["VERIFICATION FLAGS:"])
                ),
                "validation_flags": list(
                    dict.fromkeys(accumulated["VALIDATION FLAGS:"])
                ),
                "design_control_checklist": design_control_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "TRACE-GAP FLAGS:": (
                "⚠️  TRACE-GAP FLAGS (name the orphan input or output; do not assert a "
                "link absent from the supplied DHF evidence):"
            ),
            "VERIFICATION FLAGS:": (
                "⚠️  VERIFICATION FLAGS (cite the missing verification evidence for the "
                "named design output):"
            ),
            "VALIDATION FLAGS:": (
                "⚠️  VALIDATION FLAGS (cite the missing design-validation evidence for the "
                "named user need; do not substitute verification for validation):"
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
    def _build_design_control_checklist(
        request: DesignControlRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Design Assurance / Quality Engineering]")
        if accumulated["TRACE-GAP FLAGS:"]:
            checklist.append(
                "[ ] Resolve every flagged orphan input/output against the "
                "controlled requirements before design transfer"
            )
        if accumulated["VERIFICATION FLAGS:"]:
            checklist.append(
                "[ ] Attach the missing verification evidence for each flagged "
                "design output; confirm it resolves to a controlled record"
            )
        if accumulated["VALIDATION FLAGS:"]:
            checklist.append(
                "[ ] Supply design-validation evidence for each flagged user "
                "need; do not substitute verification for validation"
            )
        checklist.append(
            "[ ] Close every trace gap against the DHF before design transfer"
        )
        checklist.append(
            "[ ] Confirm V&V evidence resolves to controlled records (not draft)"
        )
        checklist.append(
            "[ ] Update the ISO 14971 risk-management file for any control "
            "lacking confirming V&V"
        )
        checklist.append(
            "[ ] Obtain Design Assurance sign-off before design freeze"
        )
        return checklist
