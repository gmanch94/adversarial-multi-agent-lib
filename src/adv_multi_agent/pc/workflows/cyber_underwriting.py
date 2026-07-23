"""
Workflow — Cyber Risk Underwriting (P&C Insurance Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to standalone
cyber insurance underwriting. Executor drafts cyber bind terms; reviewer
(recommended: different model family per ARIS §2.1 principle 1) challenges
control attestations against external evidence, sub-limit calibration,
and portfolio aggregation exposure.

Triple-flag gate (D-PC-4): CONTROL-GAP FLAGS, SUB-LIMIT FLAGS,
AGGREGATION FLAGS. **No reviewer veto** — emerging-risk line, capacity-
and-control discipline is the gate.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Live control-evidence feed — control_evidence is free-text;
       production needs structured ingestion from third-party scanners
       (BitSight, SecurityScorecard, RiskIQ) for attestation cross-check.
    2. Portfolio aggregation engine — aggregation_context must reflect
       live portfolio concentration by industry, cloud-provider, and
       common-vendor exposure.
    3. Threat-intelligence feed — ransomware sub-limit calibration should
       incorporate live ransomware-actor activity and industry-vertical
       targeting trends.
    4. Regulatory landscape engine — privacy / breach-notification
       sub-limits should reflect jurisdiction-specific regulator scope
       (HIPAA, GLBA, state breach laws, EU GDPR, biometric statutes).
    5. War / cyber-terrorism exclusion routing — post-Merck-vs-Ace and
       post-Lloyd's-LMA5564 the war-exclusion question is live; production
       needs structured rules for state-actor attribution scenarios.
    6. Sub-limit per-coverage authority — production must route sub-limit
       proposals against an authority matrix.
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

# L-PC-3: per-field cap (see claims_reserve.py for rationale).
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated cyber underwriting recommendation "
    "is not an authorised quote or bind. A credentialed cyber underwriter "
    "must verify control attestations against external scan evidence, "
    "calibrate sub-limits against threat-intelligence, and confirm "
    "portfolio aggregation discipline before any bind is communicated."
)

_CYBER_REVIEW_CRITERIA = """\
Evaluate this cyber underwriting recommendation on four dimensions.
Score each 0–10.

1. CONTROL-EVIDENCE FIDELITY (35%) — CRITICAL
   Are the applicant's attested controls supported by control_evidence
   (third-party scan, audit, attestation)? Are attestation-vs-evidence
   gaps surfaced? Are missing baseline controls for industry / size
   identified (MFA on privileged accounts, EDR on endpoints, immutable
   backups, vendor-management programme)? Flag every control-attestation
   gap under CONTROL-GAP FLAGS:.

2. SUB-LIMIT CALIBRATION (30%) — CRITICAL
   Is the ransomware sub-limit aligned with backup-immutability evidence?
   Is the regulatory-defence sub-limit appropriate for the applicant's
   regulated-data footprint? Are social-engineering / funds-transfer-fraud
   sub-limits calibrated to revenue and transaction volume? Are war /
   cyber-terrorism exclusions current per LMA5564 / Merck post-NotPetya
   wording? Flag every sub-limit miscalibration under SUB-LIMIT FLAGS:.

3. PORTFOLIO AGGREGATION (25%) — CRITICAL
   Does this bind breach industry-vertical, cloud-provider, or common-
   vendor concentration caps? Is systemic-event exposure (SolarWinds-class,
   MOVEit-class) addressed in the portfolio context? Flag every aggregation
   issue under AGGREGATION FLAGS:.

4. ACTIONABILITY (10%)
   Are the bind terms specific enough for the underwriter assistant to
   execute? Is the cyber-incident-response retainer named?

Overall score = weighted average.
Score ≥ 7.5 AND zero CONTROL-GAP FLAGS AND zero SUB-LIMIT FLAGS AND zero
AGGREGATION FLAGS: recommendation is ready for senior-underwriter review.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  CONTROL-GAP FLAGS: [bullet list, or "None detected"]
  SUB-LIMIT FLAGS: [bullet list, or "None detected"]
  AGGREGATION FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a cyber underwriting recommendation for a senior
cyber underwriter to review. You have no stake in the outcome. Your job
is to set bind terms that match the applicant's actual control maturity,
not their attested maturity — and to respect portfolio aggregation
discipline.

BASE THE TERMS ON THE INPUT DATA.

SUBMISSION DATA:
{request_text}

{wiki_context}

Produce a structured cyber underwriting recommendation with exactly
these sections:

## Applicant Summary
Industry, revenue, employee count, data-volume estimate (records held),
regulated-data footprint.

## Control Maturity Assessment
For each baseline control (MFA, EDR, immutable backup, vendor
management, IR retainer, security training, patching cadence): state
attested level + corroborating evidence + residual gap.

## Proposed Bind Terms
Premium, retention, aggregate limit, and per-coverage sub-limits:
ransomware, business interruption, data restoration, privacy /
regulatory, media liability, social engineering, funds-transfer-fraud.
State the war / cyber-terrorism exclusion wording.

## Sub-Limit Justification
For each sub-limit: how is it calibrated to control maturity, revenue,
and threat landscape?

## Portfolio Aggregation Check
This applicant's industry, primary cloud provider, and material vendors;
how they compare to the portfolio concentration cap.

## IR Retainer & Vendor Panel
Name the breach-response retainer (forensics, legal, PR, notification
vendor) and any restricted-vendor language.

## Evidence Gaps
Information missing from the inputs that materially affects the terms.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this cyber underwriting recommendation. Address EVERY issue in
the reviewer's critique, especially any CONTROL-GAP FLAGS,
SUB-LIMIT FLAGS, or AGGREGATION FLAGS.

PREVIOUS RECOMMENDATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any CONTROL-GAP FLAG: either require the control as a
condition-precedent + reduce limits, or document why the gap is
acceptable given other controls.
⚠️  For any SUB-LIMIT FLAG: recalibrate the sub-limit against the
relevant exposure base + control maturity.
⚠️  For any AGGREGATION FLAG: reduce limit, decline the risk, or refer
to portfolio-management for concentration relief.
"""


@dataclass
class CyberUnderwritingRequest:
    """Structured input for the P&C cyber-underwriting workflow."""

    applicant_summary: str
    """Industry, revenue, employee count, data-volume estimate (records held)."""

    control_attestations: str
    """MFA, EDR, backup-immutability, vendor-management posture as attested
    in the cyber application."""

    control_evidence: str
    """Third-party scan results, attestation discrepancies, prior incident
    history."""

    requested_coverage: str
    """First-party (BI, data restoration, ransomware) + third-party (privacy,
    regulatory, media); limits + sub-limits being requested."""

    proposed_terms: str
    """Premium, retention, sub-limits, war / cyber-terrorism exclusion
    wording being proposed."""

    aggregation_context: str
    """Portfolio concentration by industry / cloud-provider / software vendor
    (SolarWinds-class systemic risk)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Applicant summary: {self.applicant_summary[:cap]}",
            f"Control attestations: {self.control_attestations[:cap]}",
            f"Control evidence: {self.control_evidence[:cap]}",
            f"Requested coverage: {self.requested_coverage[:cap]}",
            f"Proposed terms: {self.proposed_terms[:cap]}",
            f"Aggregation context: {self.aggregation_context[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "CONTROL-GAP FLAGS:",
    "SUB-LIMIT FLAGS:",
    "AGGREGATION FLAGS:",
)


class CyberUnderwritingWorkflow(BaseWorkflow):
    """
    Adversarial cyber-underwriting review: executor drafts bind terms →
    reviewer challenges control-evidence fidelity, sub-limit calibration,
    and portfolio aggregation → iterate.

    Convergence gate (D-PC-4):
        score ≥ threshold
        AND zero CONTROL-GAP FLAGS
        AND zero SUB-LIMIT FLAGS
        AND zero AGGREGATION FLAGS

    No reviewer veto: emerging-risk line; capacity-and-control discipline
    is the gate, not life-safety halt.
    """

    async def run(  # type: ignore[override]
        self,
        request: CyberUnderwritingRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial cyber-underwriting loop."""
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
                criteria=_CYBER_REVIEW_CRITERIA,
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

        approver_checklist = self._build_approver_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "applicant_summary": sanitize_for_prompt(
                    request.applicant_summary, max_chars=200
                ),
                "control_gap_flags": list(dict.fromkeys(accumulated["CONTROL-GAP FLAGS:"])),
                "sub_limit_flags": list(dict.fromkeys(accumulated["SUB-LIMIT FLAGS:"])),
                "aggregation_flags": list(dict.fromkeys(accumulated["AGGREGATION FLAGS:"])),
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
            "CONTROL-GAP FLAGS:": (
                "⚠️  CONTROL-GAP FLAGS (require control as condition-precedent + "
                "reduce limits, or justify the gap):"
            ),
            "SUB-LIMIT FLAGS:": (
                "⚠️  SUB-LIMIT FLAGS (recalibrate sub-limit against exposure base "
                "and control maturity):"
            ),
            "AGGREGATION FLAGS:": (
                "⚠️  AGGREGATION FLAGS (reduce limit, decline, or refer to "
                "portfolio-management for concentration relief):"
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
        request: CyberUnderwritingRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        if accumulated["CONTROL-GAP FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  CONTROL-GAP FLAGS ({len(accumulated['CONTROL-GAP FLAGS:'])}) — "
                "obtain third-party scan or require control as condition-precedent"
            )
        if accumulated["SUB-LIMIT FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  SUB-LIMIT FLAGS ({len(accumulated['SUB-LIMIT FLAGS:'])}) — "
                "recalibrate sub-limits before bind"
            )
        if accumulated["AGGREGATION FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  AGGREGATION FLAGS ({len(accumulated['AGGREGATION FLAGS:'])}) — "
                "confirm portfolio concentration availability with portfolio management"
            )
        checklist.extend([
            "[ ] Senior cyber underwriter review per company authority matrix",
            "[ ] Confirm war / cyber-terrorism exclusion wording is current (LMA5564 family)",
            "[ ] Confirm IR retainer and vendor-panel restrictions",
            "[ ] Confirm portfolio aggregation pre-clearance for cloud / vendor concentration",
            "[ ] Issue bind — AI output must not trigger automatic quote / bind",
        ])
        return checklist
