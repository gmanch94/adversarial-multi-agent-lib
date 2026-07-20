"""
Workflow — Premarket Device Cybersecurity Review (Lifesciences · Devices)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for FDA premarket device
cybersecurity. Executor summarizes the threat model, SBOM, and patchability
posture; reviewer (recommended: different model family) challenges an
unaddressed attack surface, an SBOM gap or unresolved vulnerability, and a
component with no field-update path.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Threat-modeling tool — the attack-surface analysis should resolve against
       the controlled threat-model artifact, not caller-pasted text.
    2. SBOM-generation + vulnerability-scanning pipeline — the software bill of
       materials and its vulnerabilities should be produced by the controlled
       build/scan pipeline, not a manual summary.
    3. Secure-update / PKI infrastructure — the patchability posture should
       resolve against the controlled update service and signing infrastructure.
    4. Premarket-submission documentation system — the cybersecurity package
       should resolve against the controlled submission repository.
    5. Qualified approver gate — every AI-suggested cybersecurity conclusion must
       be reviewed by a qualified Product Security lead and Regulatory Affairs.
       Output is never an auto-submitted cybersecurity package.
    6. Dedicated third-model security auditor — production should use a
       separately configured auditor model for threat-model bias detection.
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

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated premarket device cybersecurity review is "
    "decision-support, not a regulatory submission and not a security "
    "certification. A qualified Product Security lead and Regulatory Affairs must "
    "independently confirm the threat model, SBOM, and patchability posture "
    "before any premarket cybersecurity package is submitted. Not legal or "
    "medical advice."
)

_CYBERSECURITY_REVIEW_CRITERIA = """\
Evaluate this premarket device cybersecurity review on five dimensions. Score each 0–10.

1. THREAT-MODEL COMPLETENESS (30%) — CRITICAL
   Does every attack surface (interfaces, data flows, trust boundaries) have a
   security control addressing its threats? Penalise a threat or attack surface
   with no addressing control. Flag under THREAT-MODEL FLAGS:.

2. SBOM & VULNERABILITY MANAGEMENT (25%) — CRITICAL
   Is the software bill of materials complete, and is every known component
   vulnerability resolved or risk-accepted with justification? Penalise a missing
   component or an unresolved known vulnerability. Flag under SBOM-GAP FLAGS:.

3. PATCHABILITY / LIFECYCLE (20%) — CRITICAL
   Does every component that will need security patches over the device lifecycle
   have a field-update path? Penalise a component with no update mechanism. Flag
   under PATCHABILITY FLAGS:.

4. SECURITY-CONTROL ADEQUACY (15%)
   Are the security controls (authentication, encryption, integrity) proportionate
   to risk and linked to safety/essential performance? Penalise controls not
   matched to the risk.

5. ACTIONABILITY (10%)
   Is each finding specific enough for the security team to act on (which surface,
   which component, which control)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero THREAT-MODEL FLAGS AND zero SBOM-GAP FLAGS AND zero
PATCHABILITY FLAGS: ready for Product Security sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  THREAT-MODEL FLAGS: [bullet list, or "None detected"]
  SBOM-GAP FLAGS: [bullet list, or "None detected"]
  PATCHABILITY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are reviewing a premarket device cybersecurity package for a Product Security
lead to approve. You have no stake in the outcome. Assess the threat model, the
SBOM and its vulnerabilities, and the patchability posture — grounded only in the
data supplied, not general security norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert an attack surface,
component, or vulnerability that is not present below.

CYBERSECURITY PACKAGE (caller-supplied — verify against the controlled
threat-model/SBOM/update systems before acting):
{request_text}

{wiki_context}

Produce a review with:

## Threat-model coverage
- Each attack surface and the control(s) addressing it; name every gap

## SBOM and vulnerability status
- Component completeness and each known vulnerability's resolution (or the gap)

## Patchability posture
- Each component's field-update path (or the gap)

## Security-control adequacy
- Whether controls are proportionate to risk and tied to safety/essential performance

## Gaps and recommendations
- Specific, closeable gaps (which surface, which component, which control)

## Claims
- Specific factual claims about the cybersecurity package that ground the review
"""

_REVISION_PROMPT = """\
Revise the premarket device cybersecurity review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact attack surface, SBOM component, or
un-patchable component from the supplied package; do not assert one not in the input.
"""


@dataclass
class PremarketCybersecurityRequest:
    """Structured input for the premarket device cybersecurity review workflow."""

    device_description: str
    """Generic connected-device category and its interfaces."""

    intended_use_environment: str
    """Clinical / home network context the device operates in."""

    threat_model_summary: str
    """Attack-surface / threat analysis (e.g. STRIDE)."""

    security_controls: str
    """Authentication, encryption, and integrity controls."""

    sbom_summary: str
    """Software bill of materials + third-party / OSS components."""

    vulnerability_assessment: str
    """Known vulnerabilities in the components and their status."""

    patchability_plan: str
    """How the device receives security updates over its lifecycle."""

    residual_risk_summary: str
    """Residual cyber risk to safety / essential performance."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Device description: {self.device_description[:cap]}",
            f"Intended use environment: {self.intended_use_environment[:cap]}",
            f"Threat model summary: {self.threat_model_summary[:cap]}",
            f"Security controls: {self.security_controls[:cap]}",
            f"SBOM summary: {self.sbom_summary[:cap]}",
            f"Vulnerability assessment: {self.vulnerability_assessment[:cap]}",
            f"Patchability plan: {self.patchability_plan[:cap]}",
            f"Residual risk summary: {self.residual_risk_summary[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "THREAT-MODEL FLAGS:",
    "SBOM-GAP FLAGS:",
    "PATCHABILITY FLAGS:",
)


class PremarketCybersecurityWorkflow(BaseWorkflow):
    """
    Adversarial premarket device cybersecurity review: executor assesses the
    threat model, SBOM, and patchability → reviewer challenges an unaddressed
    attack surface, an SBOM gap or unresolved vulnerability, and an un-patchable
    component → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero THREAT-MODEL FLAGS
        AND zero SBOM-GAP FLAGS
        AND zero PATCHABILITY FLAGS

    No reviewer veto — premarket cybersecurity corrections are reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: PremarketCybersecurityRequest,
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
                criteria=_CYBERSECURITY_REVIEW_CRITERIA,
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

        cybersecurity_checklist = self._build_cybersecurity_checklist(
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
                "threat_model_flags": list(
                    dict.fromkeys(accumulated["THREAT-MODEL FLAGS:"])
                ),
                "sbom_gap_flags": list(dict.fromkeys(accumulated["SBOM-GAP FLAGS:"])),
                "patchability_flags": list(
                    dict.fromkeys(accumulated["PATCHABILITY FLAGS:"])
                ),
                "cybersecurity_checklist": cybersecurity_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "THREAT-MODEL FLAGS:": (
                "⚠️  THREAT-MODEL FLAGS (name the attack surface or threat with no "
                "addressing control):"
            ),
            "SBOM-GAP FLAGS:": (
                "⚠️  SBOM-GAP FLAGS (name the missing component or the unresolved "
                "known vulnerability):"
            ),
            "PATCHABILITY FLAGS:": (
                "⚠️  PATCHABILITY FLAGS (name the component that will need patches "
                "but has no field-update path):"
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
    def _build_cybersecurity_checklist(
        request: PremarketCybersecurityRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Product Security / Regulatory]"]
        if accumulated["THREAT-MODEL FLAGS:"]:
            checklist.append(
                "[ ] Add a control for every flagged attack surface / threat "
                "before submission"
            )
        if accumulated["SBOM-GAP FLAGS:"]:
            checklist.append(
                "[ ] Complete the SBOM and resolve or justify every flagged "
                "component vulnerability"
            )
        if accumulated["PATCHABILITY FLAGS:"]:
            checklist.append(
                "[ ] Define a field-update path for every flagged component that "
                "will need security patches"
            )
        checklist.extend([
            "[ ] Confirm the threat model covers every interface and trust boundary",
            "[ ] Confirm the SBOM resolves against the controlled build/scan pipeline",
            "[ ] Confirm each security control ties to safety / essential performance",
            "[ ] Obtain Product Security and Regulatory Affairs sign-off before submission",
        ])
        return checklist
