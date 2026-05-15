"""
Workflow — Product Liability Root-Cause (Industrial Manufacturing Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to product-
liability root-cause attribution for an industrial-equipment field
incident (tipover, pedestrian-strike, struck-by, fire, mechanical failure
with injury or property damage).

Executor drafts a root-cause attribution; reviewer (recommended:
different model family per ARIS §2.1 principle 1) challenges
"operator error" attribution that may mask a design-defect signal, and
can issue a REVIEWER VETO when the draft attributes to operator but the
evidence supports a design-defect or warning-adequacy gap.

Veto + triple-flag gate (D-IND-1): DESIGN-DEFECT FLAGS, OPERATOR-ERROR
FLAGS, WARNING-ADEQUACY FLAGS, plus **reviewer veto**. Design-defect
attribution drives recall scope (downstream RecallScopeManufacturingWorkflow)
and product-liability reserve (pc.ClaimsReserveWorkflow), so the veto
fires on convenient operator-error attribution that masks engineering signal.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. CMMS / FRACAS / customer-quality-feedback integration — field
       failure-mode evidence must come from a structured failure-reporting
       system with mode-effect linkage, not paraphrased prose.
    2. Telematics integration — duty-cycle, shock event, and operator-
       input traces from the equipment's telematics platform (Crown
       InfoLink, Hyster Tracker, Linde connect:) provide ground truth for
       operator-vs-design attribution.
    3. Standards library — ANSI / ITSDF B56.x, ISO 3691-x, OSHA 1910.178,
       and applicable PALD / EU machinery directive citations must come
       from a structured standards corpus.
    4. PFMEA / DFMEA linkage — every confirmed design-defect cause must
       update the FMEA risk-priority number; not done here.
    5. Warning-adequacy methodology — the warning / placard / training
       adequacy review needs structured methodology (HFE / ANSI Z535)
       evidence.
    6. Append-only audit store — every draft, flag, and veto must be
       captured in a tamper-evident store defensible against CPSC § 15(b)
       and product-liability discovery.
    7. Dedicated third-model engineering auditor — see ARIS §3.1.
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
    "⚠️  ADVISORY ONLY — This AI-generated product-liability root-cause "
    "attribution is not an authorised legal or regulatory position. A "
    "credentialed product-safety engineer, in-house counsel, and (where "
    "applicable) outside product-liability counsel must verify the "
    "attribution against telematics evidence, field failure-mode "
    "records, and applicable standards before any defence position or "
    "CPSC § 15(b) report is filed. AI output must never trigger an "
    "automated regulatory notification."
)

_VETO_BANNER = (
    "⚠️  REVIEWER VETO — workflow halted before convergence. "
    "See metadata['veto_reason']. Escalate to product-safety committee + "
    "in-house counsel BEFORE filing any defence position or regulator "
    "notice; design-defect or warning-adequacy signal may be masked by "
    "an operator-error attribution."
)

_PRODLIAB_REVIEW_CRITERIA = """\
Evaluate this product-liability root-cause attribution on four dimensions.
Score each 0–10.

1. DESIGN-DEFECT ANALYSIS (35%) — CRITICAL
   Is the design analysed for foreseeable-misuse tolerance? Are the
   applicable standards (ANSI / ITSDF B56.x, ISO 3691-x, OSHA 1910.178)
   compared against the as-built configuration? Are similar field-failure
   patterns from other units of the same model considered? Penalise
   attributions that dismiss design as a cause without evidence. Flag
   every gap under DESIGN-DEFECT FLAGS:.

2. OPERATOR-ERROR INTEGRITY (30%) — CRITICAL
   If operator action is cited as a cause, is it supported by telematics /
   video / witness evidence, AND is the operator's action one that
   reasonable design would prevent or tolerate? Is the operator-error
   attribution consistent with training-of-record and the operator
   manual? Penalise convenient operator-blame that ignores design
   foreseeability. Flag every gap under OPERATOR-ERROR FLAGS:.

3. WARNING / TRAINING ADEQUACY (25%) — CRITICAL
   Was the warning / placard / operator-manual instruction adequate
   (legible, age-appropriate, in operator's language, conspicuous,
   present at point of risk)? Was the training-of-record applicable to
   the task being performed? Penalise warning hand-waving. Flag every
   gap under WARNING-ADEQUACY FLAGS:.

4. ACTIONABILITY (10%)
   Are the next actions (product-safety committee escalation, field-bulletin,
   CPSC § 15(b) substantial-product-hazard decision input, PFMEA update,
   counsel engagement) specific enough for the safety committee to execute?

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Draft attributes to operator-error but telematics / video / similar-unit
    field-failure evidence supports a design-defect signal.
  • Draft attributes to operator-error but the operator's action is a
    foreseeable misuse the design fails to tolerate (per ANSI / ISO
    foreseeable-misuse principles).
  • Draft makes no design-defect analysis when the field-failure population
    shows a non-random spatial / temporal pattern.
  • Draft dismisses warning / training adequacy without evidence that the
    warning was present, legible, and applicable.
  • Confirmed injury severity is catastrophic (fatality, permanent
    disability, severe burn) AND no parallel CPSC § 15(b) substantial-
    product-hazard analysis is proposed.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto directive continuation line with
"Overall", "Key issues", or a markdown header (#) — those markers terminate
the veto block in the parser.

Overall score = weighted average.
Score ≥ 7.5 AND zero DESIGN-DEFECT FLAGS AND zero OPERATOR-ERROR FLAGS AND
zero WARNING-ADEQUACY FLAGS AND no VETO: attribution is ready for
product-safety review. Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  DESIGN-DEFECT FLAGS: [bullet list, or "None detected"]
  OPERATOR-ERROR FLAGS: [bullet list, or "None detected"]
  WARNING-ADEQUACY FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are preparing a product-liability root-cause attribution for an
industrial OEM's product-safety committee. You have no stake in the
outcome. Your job is to attribute the field incident to its true root
cause with evidence — not to land on operator-error for litigation
convenience, not to over-call design-defect for cautious defaults.

BASE THE ATTRIBUTION ON THE INPUT DATA.

INCIDENT DATA:
{request_text}

{wiki_context}

Produce a structured attribution with exactly these sections:

## Incident Summary
Restate the incident: date, location, equipment serial, mechanism,
injuries / damage, evidence chain-of-custody.

## Telematics and Trace Evidence
Summarise duty-cycle, shock-event, operator-input, and any video / on-board
event-data-recorder traces. Note gaps explicitly.

## Standards Comparison
Compare the as-built equipment configuration against the applicable
standards (ANSI / ITSDF B56.x, ISO 3691-x, OSHA 1910.178). Flag any
non-conformance.

## Foreseeable-Misuse Analysis
For each operator-action candidate cause: is the action a foreseeable
misuse the design should tolerate? Cite the standard or industry-
practice basis.

## Design-Defect Hypothesis
For each design candidate cause: build the hypothesis with field-failure
population evidence and engineering reasoning. State adjacent-unit
exposure.

## Operator-Error Attribution (if any)
If operator action is cited as the cause: state the evidence trail
(telematics + video + training-of-record + warning conspicuity). Do not
cite operator error if the evidence does not exclude design or warning
inadequacy.

## Warning / Training Adequacy
Review the warnings / placards / operator-manual instructions and training-
of-record against ANSI Z535 / HFE principles. Cite specifics.

## Attribution and Next Actions
Final attribution split (design / operator / warning / mixed). Next
actions: product-safety committee escalation, field-bulletin, CPSC §
15(b) substantial-product-hazard decision input, PFMEA update, counsel
engagement.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this product-liability root-cause attribution. Address EVERY issue
in the reviewer's critique, especially any DESIGN-DEFECT FLAGS,
OPERATOR-ERROR FLAGS, or WARNING-ADEQUACY FLAGS.

PREVIOUS ATTRIBUTION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any DESIGN-DEFECT FLAG: deepen the design analysis with foreseeable-
misuse tolerance + standards comparison + adjacent-unit pattern.
⚠️  For any OPERATOR-ERROR FLAG: produce telematics / video / training-of-
record evidence supporting the attribution, or remove the operator-error
claim.
⚠️  For any WARNING-ADEQUACY FLAG: review the warning conspicuity /
legibility / language / placement against ANSI Z535 evidence, or revise
the attribution.
"""


@dataclass
class ProductLiabilityRootCauseRequest:
    """Structured input for the product-liability root-cause workflow."""

    incident_summary: str
    """Date, location, serial, mechanism, injuries / damage, chain-of-custody."""

    telematics_and_trace: str
    """Duty-cycle, shock-event, operator-input, video / EDR traces, gaps."""

    equipment_configuration: str
    """As-built configuration, options, recent ECOs applied to this serial."""

    standards_context: str
    """Applicable standards (ANSI / ITSDF B56.x, ISO 3691-x, OSHA 1910.178),
    EU directives where applicable."""

    operator_and_training: str
    """Operator identification, training-of-record applicable to the task,
    duty-cycle history, prior incident history if any."""

    field_failure_population: str
    """Pattern across other units of the same model (similar serials,
    similar mechanisms, time-on-equipment distribution)."""

    initial_attribution: str
    """Investigator's first-pass attribution + supporting reasoning."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Incident summary: {self.incident_summary[:cap]}",
            f"Telematics and trace: {self.telematics_and_trace[:cap]}",
            f"Equipment configuration: {self.equipment_configuration[:cap]}",
            f"Standards context: {self.standards_context[:cap]}",
            f"Operator and training: {self.operator_and_training[:cap]}",
            f"Field failure population: {self.field_failure_population[:cap]}",
            f"Initial attribution: {self.initial_attribution[:cap]}",
        ])


class ProductLiabilityRootCauseWorkflow(BaseWorkflow):
    """
    Adversarial product-liability root-cause attribution: executor drafts
    an attribution → reviewer challenges design-defect coverage, operator-
    error integrity, and warning adequacy, with the power to VETO →
    iterate.

    Convergence gate (D-IND-1, mirroring D-RETAIL-1):
        score ≥ threshold
        AND zero DESIGN-DEFECT FLAGS
        AND zero OPERATOR-ERROR FLAGS
        AND zero WARNING-ADEQUACY FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately, recording the verbatim veto
    directive in metadata['veto_reason']. Score and flags from the vetoed
    round are also captured.
    """

    async def run(  # type: ignore[override]
        self,
        request: ProductLiabilityRootCauseRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_design_flags: list[str] = []
        current_operator_flags: list[str] = []
        current_warning_flags: list[str] = []
        all_design_flags: list[str] = []
        all_operator_flags: list[str] = []
        all_warning_flags: list[str] = []
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
                    current_design_flags,
                    current_operator_flags,
                    current_warning_flags,
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
                criteria=_PRODLIAB_REVIEW_CRITERIA,
            )
            score = review.score
            current_design_flags = extract_flags(review.critique, "DESIGN-DEFECT FLAGS:")
            current_operator_flags = extract_flags(review.critique, "OPERATOR-ERROR FLAGS:")
            current_warning_flags = extract_flags(
                review.critique, "WARNING-ADEQUACY FLAGS:"
            )
            all_design_flags.extend(current_design_flags)
            all_operator_flags.extend(current_operator_flags)
            all_warning_flags.extend(current_warning_flags)

            # Audit-trail writes happen BEFORE the veto check — required by
            # CPSC § 15(b) and product-liability discovery.
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
                and not current_design_flags
                and not current_operator_flags
                and not current_warning_flags
            ):
                converged = True
                break

        safety_checklist = self._build_safety_checklist(
            request,
            all_design_flags,
            all_operator_flags,
            all_warning_flags,
            veto_reason,
        )

        output_with_banners = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "incident_summary": request.incident_summary,
            "design_defect_flags": list(dict.fromkeys(all_design_flags)),
            "operator_error_flags": list(dict.fromkeys(all_operator_flags)),
            "warning_adequacy_flags": list(dict.fromkeys(all_warning_flags)),
            "safety_checklist": safety_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True

        return WorkflowResult(
            output=output_with_banners,
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
        design_flags: list[str],
        operator_flags: list[str],
        warning_flags: list[str],
    ) -> str:
        if not design_flags and not operator_flags and not warning_flags:
            return ""
        parts: list[str] = []
        if design_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(design_flags)
            )
            parts.append(
                "⚠️  DESIGN-DEFECT FLAGS (deepen design analysis with "
                "foreseeable-misuse + standards + adjacent-unit pattern):\n"
                f"{flags_text}"
            )
        if operator_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(operator_flags)
            )
            parts.append(
                "⚠️  OPERATOR-ERROR FLAGS (produce telematics / video / "
                "training-of-record evidence or remove the operator-error "
                "claim):\n"
                f"{flags_text}"
            )
        if warning_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(warning_flags)
            )
            parts.append(
                "⚠️  WARNING-ADEQUACY FLAGS (review warning conspicuity / "
                "legibility / language / placement against ANSI Z535 "
                "evidence):\n"
                f"{flags_text}"
            )
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _compose_output(draft: str, veto_reason: str | None) -> str:
        if veto_reason is None:
            return f"{draft}\n\n---\n\n{_DISCLAIMER}"
        return f"{draft}\n\n---\n\n{_VETO_BANNER}\n\n{_DISCLAIMER}"

    @staticmethod
    def _build_safety_checklist(
        request: ProductLiabilityRootCauseRequest,
        design_flags: list[str],
        operator_flags: list[str],
        warning_flags: list[str],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = []
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — escalate to product-safety committee + "
                "in-house counsel BEFORE filing any defence or regulator notice"
            )
        if design_flags:
            checklist.append(
                f"[ ] ⚠️  DESIGN-DEFECT FLAGS ({len(design_flags)}) — re-open "
                "design analysis with foreseeable-misuse + standards comparison"
            )
        if operator_flags:
            checklist.append(
                f"[ ] ⚠️  OPERATOR-ERROR FLAGS ({len(operator_flags)}) — "
                "verify telematics / video / training-of-record evidence"
            )
        if warning_flags:
            checklist.append(
                f"[ ] ⚠️  WARNING-ADEQUACY FLAGS ({len(warning_flags)}) — "
                "review warnings against ANSI Z535 / HFE principles"
            )
        checklist.extend([
            "[ ] Product-safety committee sign-off",
            "[ ] In-house counsel review (and outside product-liability counsel if litigation likely)",
            "[ ] CPSC § 15(b) substantial-product-hazard decision input prepared",
            "[ ] Field-failure-population query for adjacent serials",
            "[ ] PFMEA update if design contribution confirmed",
            "[ ] Trigger RecallScopeManufacturingWorkflow if design-defect confirmed",
            "[ ] Trigger pc.ClaimsReserveWorkflow for liability reserve",
            f"[ ] Confirm standards comparison: {request.standards_context[:60]}",
            "[ ] File regulator notice / defence position — AI output must not trigger automatic filing",
        ])
        return checklist
