"""
Workflow — Clinical Protocol Design Review (Lifesciences · Pharma/Device, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to clinical protocol
design: executor reviews a study protocol (endpoint validity, statistical power,
safety monitoring); reviewer (cross-model per ARIS §2.1) challenges invalid
endpoints, inadequate power, and insufficient safety monitoring, with the power
to VETO when the protocol exposes subjects to undue risk or cannot support its
primary objective.

Veto gate (D-LIFESCI-4): fires when the protocol exposes subjects to undue risk
(inadequate safety monitoring / stopping rules for a known serious risk) or is
scientifically invalid such that it cannot support its primary objective — an
IRB / ethics committee should withhold approval.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. CTMS — the protocol and its version should resolve against the controlled
       clinical trial management system, not caller-pasted text.
    2. Biostatistics tooling — power and sample-size calculations should be
       produced by validated biostatistics tooling, not asserted in free text.
    3. IRB / EC submission system — no protocol proceeds to conduct without IRB /
       ethics-committee approval; this workflow does not submit.
    4. DSMB charter repository — safety-monitoring and stopping rules should
       resolve against the controlled DSMB charter.
    5. Qualified approver gate — every AI-suggested finding must be reviewed and
       confirmed by a qualified Clinical Development lead / Medical Monitor;
       output is never a study protocol of record.
    6. Dedicated third-model protocol auditor — production should use a
       separately configured auditor model for endpoint/power bias detection.
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
    "ADVISORY ONLY — This AI-generated clinical protocol design review is "
    "decision-support, not a study protocol and not an ethics submission. A "
    "qualified Clinical Development lead / Medical Monitor must independently "
    "confirm endpoint validity, statistical power, and safety monitoring, and "
    "IRB / ethics-committee approval is required, before the protocol proceeds. "
    "Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found the "
    "protocol exposes subjects to undue risk or cannot support its primary "
    "objective as designed. See metadata['veto_reason']. Escalate to the Medical "
    "Monitor / IRB; the protocol must not proceed to submission as designed."
)

_FLAG_HEADERS = ("ENDPOINT FLAGS:", "POWER FLAGS:", "SAFETY-MONITORING FLAGS:")

_CLINICAL_PROTOCOL_REVIEW_CRITERIA = """\
Evaluate this clinical protocol design review on five dimensions. Score each 0–10.

1. ENDPOINT VALIDITY (30%) — CRITICAL
   Is the primary endpoint validated and able to support the study objective (no
   misused surrogate)? Penalise an endpoint that cannot support the objective.
   Flag under ENDPOINT FLAGS:.

2. STATISTICAL POWER (25%) — CRITICAL
   Is the sample size and power adequate to detect the effect, with justified
   assumptions? Penalise an underpowered design or unjustified effect-size
   assumptions. Flag under POWER FLAGS:.

3. SAFETY MONITORING (20%) — CRITICAL
   Are the safety-monitoring plan and stopping rules adequate for the known
   risks (DSMB, pre-specified stopping rules)? Penalise inadequate monitoring for
   a known serious risk. Flag under SAFETY-MONITORING FLAGS:.

4. ETHICS / POPULATION-APPROPRIATENESS (15%)
   Is the eligibility appropriate and proportionate to the risk, with safeguards
   for any vulnerable population? Penalise eligibility that exposes subjects
   without justification.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which endpoint, which assumption,
   which stopping rule)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the protocol exposes subjects to undue risk (inadequate safety
monitoring / stopping rules for a known serious risk) or is scientifically
invalid such that it cannot support its primary objective.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero ENDPOINT FLAGS AND zero POWER FLAGS AND zero
SAFETY-MONITORING FLAGS AND no VETO: ready for Clinical Development sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  ENDPOINT FLAGS: [bullet list, or "None detected"]
  POWER FLAGS: [bullet list, or "None detected"]
  SAFETY-MONITORING FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are producing a clinical protocol design review for a qualified Clinical
Development lead / Medical Monitor. You have no stake in the outcome. Your job is
to judge endpoint validity, statistical power, and safety monitoring — grounded
only in the protocol data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

PROTOCOL DATA:
{request_text}

{wiki_context}

Produce a structured review with exactly these sections:

## Protocol summary
Summarise the indication, phase, and design from the input.

## Endpoint validity
State whether the primary endpoint is validated and able to support the study
objective; name any misused surrogate.

## Statistical power
State whether the sample size and power are adequate, and whether the effect-size
assumptions are justified.

## Safety monitoring
State whether the safety-monitoring plan and stopping rules are adequate for the
known risks.

## Ethics and population
State whether eligibility is appropriate and proportionate to the risk.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this clinical protocol design review. Address EVERY issue in the
reviewer's critique, especially any ENDPOINT FLAGS, POWER FLAGS, or
SAFETY-MONITORING FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any ENDPOINT flag: re-assess whether the endpoint supports the objective.
⚠️  For any POWER flag: re-justify the sample size and effect-size assumptions.
⚠️  For any SAFETY-MONITORING flag: strengthen the monitoring / stopping rules for
the known risk.
"""


@dataclass
class ClinicalProtocolRequest:
    """Structured input for the clinical protocol design review workflow."""

    protocol_synopsis: str
    """Generic indication, phase, and study design."""

    primary_endpoint: str
    """The primary endpoint and its measurement."""

    secondary_endpoints: str
    """Secondary / exploratory endpoints."""

    statistical_plan_summary: str
    """Power, sample size, and analysis plan."""

    population_eligibility: str
    """Inclusion / exclusion criteria and population."""

    safety_monitoring_plan: str
    """DSMB, stopping rules, and safety monitoring."""

    known_risks: str
    """The product's known safety profile / risks."""

    comparator_control: str
    """Comparator / control arm design."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Protocol synopsis: {self.protocol_synopsis[:cap]}",
            f"Primary endpoint: {self.primary_endpoint[:cap]}",
            f"Secondary endpoints: {self.secondary_endpoints[:cap]}",
            f"Statistical plan summary: {self.statistical_plan_summary[:cap]}",
            f"Population eligibility: {self.population_eligibility[:cap]}",
            f"Safety monitoring plan: {self.safety_monitoring_plan[:cap]}",
            f"Known risks: {self.known_risks[:cap]}",
            f"Comparator control: {self.comparator_control[:cap]}",
        ])


class ClinicalProtocolDesignWorkflow(BaseWorkflow):
    """
    Adversarial clinical protocol design review: executor reviews endpoint +
    power + safety monitoring → reviewer challenges invalid endpoints, inadequate
    power, and insufficient safety monitoring, with the power to VETO → iterate.

    Convergence gate (D-LIFESCI-4):
        score ≥ threshold (8.0)
        AND zero ENDPOINT FLAGS
        AND zero POWER FLAGS
        AND zero SAFETY-MONITORING FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: ClinicalProtocolRequest,
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
                criteria=_CLINICAL_PROTOCOL_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            # Audit-trail writes happen BEFORE the veto check — preserves the
            # round-N draft in wiki + ledger even if vetoed (D-LIFESCI-4).
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

        clinical_protocol_checklist = self._build_clinical_protocol_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "protocol_synopsis": sanitize_for_prompt(
                request.protocol_synopsis, max_chars=200
            ),
            "endpoint_flags": list(dict.fromkeys(accumulated["ENDPOINT FLAGS:"])),
            "power_flags": list(dict.fromkeys(accumulated["POWER FLAGS:"])),
            "safety_monitoring_flags": list(
                dict.fromkeys(accumulated["SAFETY-MONITORING FLAGS:"])
            ),
            "clinical_protocol_checklist": clinical_protocol_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the Medical Monitor sees what the AI produced before the REVIEWER
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
            "ENDPOINT FLAGS:": (
                "⚠️  ENDPOINT FLAGS (re-assess whether the endpoint supports the "
                "objective):"
            ),
            "POWER FLAGS:": (
                "⚠️  POWER FLAGS (re-justify the sample size and effect-size "
                "assumptions):"
            ),
            "SAFETY-MONITORING FLAGS:": (
                "⚠️  SAFETY-MONITORING FLAGS (strengthen the monitoring / stopping "
                "rules for the known risk):"
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
    def _build_clinical_protocol_checklist(
        request: ClinicalProtocolRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Clinical Development / Medical Monitor]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — the protocol exposes subjects to undue risk "
                "or cannot support its primary objective; escalate to the Medical "
                "Monitor / IRB and do not proceed as designed"
            )
        endpoint_flags = accumulated.get("ENDPOINT FLAGS:", [])
        power_flags = accumulated.get("POWER FLAGS:", [])
        safety_monitoring_flags = accumulated.get("SAFETY-MONITORING FLAGS:", [])
        if endpoint_flags:
            checklist.append(
                f"[ ] ⚠️  ENDPOINT FLAGS ({len(endpoint_flags)}) — re-assess whether "
                "the endpoint supports the objective"
            )
        if power_flags:
            checklist.append(
                f"[ ] ⚠️  POWER FLAGS ({len(power_flags)}) — re-justify the sample "
                "size and effect-size assumptions"
            )
        if safety_monitoring_flags:
            checklist.append(
                f"[ ] ⚠️  SAFETY-MONITORING FLAGS ({len(safety_monitoring_flags)}) — "
                "strengthen the monitoring / stopping rules for the known risk"
            )
        checklist.extend([
            "[ ] Confirm the primary endpoint is validated and supports the objective",
            "[ ] Confirm the sample size and power assumptions are justified",
            "[ ] Confirm the safety-monitoring plan and stopping rules fit the risks",
            "[ ] Obtain IRB / ethics-committee approval before the protocol proceeds",
            "[ ] Obtain Clinical Development / Medical Monitor sign-off",
        ])
        return checklist
