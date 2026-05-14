"""
Workflow — Gig-Economy Platform Liability (Specialty P&C Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to specialty
underwriting / claims for gig-economy platform liability: rideshare /
delivery / skilled-trades / on-demand-services platforms covering
1099 workers who alternate between personal and platform-on time.

This is the **specialty-lines** track of the P&C domain (see D-PC-6):
risks defined by a state-by-state regulatory patchwork (California AB5
+ Prop 22, Massachusetts and New York legislation, state TNC laws, NLRB
guidance), where worker-classification disputes can retroactively
transform the coverage stack and where the personal-vs-commercial-policy
seam during platform-on transitions is the dominant claims battleground.

Triple-flag gate (D-PC-4) + **reviewer-veto**: a proposed bind that
would survive a worker-classification audit only by accident creates
material retroactive exposure; that warrants a halt independent of
score.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. State-by-state classification rule engine — AB5 + Prop 22 (CA),
       Mass / NY AG positions, Florida TNC law, the IRS 20-factor test,
       NLRB joint-employer rulings all interact; production must encode
       them as a rule base, not paraphrase.
    2. Platform-app telemetry integration — "platform-on" status is the
       coverage trigger for most TNC-era policies; production must
       integrate platform telemetry as authoritative timestamp, not
       producer-attested.
    3. Personal-policy intersection — most worker personal auto / GL
       policies exclude commercial use; production needs structured
       coordination clauses, not prose.
    4. Occupational-accident / workers'-comp boundary — many platforms
       fund occupational-accident coverage in lieu of workers' comp;
       structured comparison vs state WC requirements is mandatory.
    5. NLRB / DOL audit-trail — the regulatory-audit regime for gig
       platforms is active; production must retain decision-tree evidence
       for every classification call.
    6. Class-action signal monitoring — gig platforms are the most-
       litigated class-action segment of recent years; live signal feed
       must inform underwriting appetite.
    7. Append-only audit store + dedicated third-model auditor — see
       ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import (
    extract_flags,
    extract_veto_directive,
    sanitize_for_prompt,
)
from ...core.workflow import BaseWorkflow, WorkflowResult

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated gig-platform liability analysis "
    "is not an authorised bind or coverage decision. Specialty platform-"
    "liability counsel and senior underwriting must verify worker "
    "classification posture, personal-policy seam treatment, and state-"
    "regulatory exposure before any bind. AI output must never trigger "
    "automated issuance."
)

_VETO_BANNER = (
    "⚠️  REVIEWER VETO — workflow halted before convergence. "
    "See metadata['veto_reason']. Escalate to platform-liability counsel "
    "immediately; do not bind or communicate this decision."
)

_GIG_REVIEW_CRITERIA = """\
Evaluate this gig-platform liability analysis on four dimensions.
Score each 0–10.

1. WORKER-CLASSIFICATION POSTURE (35%) — CRITICAL
   Does the analysis address the operating-state's classification test
   (CA ABC test under AB5 / Prop 22 carve-out; NLRB joint-employer
   guidance; IRS 20-factor; state-specific TNC frameworks)? Are
   classification-dependent coverage components (occupational-accident
   vs WC, NLRB joint-employer, employment-practices) correctly routed?
   Flag every classification gap under CLASSIFICATION FLAGS:.

2. COVERAGE-GAP COORDINATION (30%) — CRITICAL
   The platform-on / platform-off transition + worker's personal auto /
   GL / homeowners policy + platform's commercial / TNC policy create
   seams. Are the seams identified? Is "platform-on" defined consistently
   with platform-app telemetry? Are personal-policy commercial-use
   exclusions addressed? Flag every coverage-gap issue under
   COVERAGE-GAP FLAGS:.

3. REGULATORY PATCHWORK (25%) — CRITICAL
   Does the analysis address the state-by-state regulatory mix (TNC
   statutes, gig-worker classification statutes, state AG positions,
   state DOL audit posture, NLRB joint-employer determinations)? Are
   multi-state operations addressed with state-specific routing? Flag
   every regulatory-overlap miss under REGULATORY-PATCHWORK FLAGS:.

4. ACTIONABILITY (10%)
   Are next steps (platform-disclosure refresh, worker-onboarding
   coverage education, state-AG monitoring) specific enough for
   execution?

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Proposed bind would only survive a worker-classification audit by
    accident (the platform's operating model does NOT match the
    classification it claims) AND retroactive coverage exposure has not
    been priced.
  • Personal-policy carve-out / commercial-use exclusion creates a
    coverage gap during platform-on time AND the gap is not bridged by
    the proposed bind.
  • A material multi-state classification dispute is pending against the
    platform (state AG, NLRB, class action) AND the analysis treats the
    platform's preferred classification as settled.
  • Occupational-accident benefit structure substitutes for state-
    mandated workers' comp AND state law does not permit the
    substitution.
Otherwise: "REVIEWER VETO: None".

Overall score = weighted average.
Score ≥ 7.5 AND zero CLASSIFICATION FLAGS AND zero COVERAGE-GAP FLAGS
AND zero REGULATORY-PATCHWORK FLAGS AND no VETO: bind is ready for
senior-underwriter review.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  CLASSIFICATION FLAGS: [bullet list, or "None detected"]
  COVERAGE-GAP FLAGS: [bullet list, or "None detected"]
  REGULATORY-PATCHWORK FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are preparing a gig-platform liability analysis for specialty
platform-liability counsel and a senior underwriter to review. You have
no stake in the outcome. Your job is to test the proposed bind against
the operating-state's classification rule, identify personal-vs-platform
coverage seams, and surface the state-regulatory patchwork — not to
chase the platform's preferred narrative.

BASE THE ANALYSIS ON THE INPUT DATA.

PLATFORM DATA:
{request_text}

{wiki_context}

Produce a structured analysis with exactly these sections:

## Platform & Workforce Summary
Platform business model, state(s) of operation, worker count, worker
mix (1099 / W-2 / employee-vs-contractor disputed?), service type.

## Worker-Classification Posture
For each state of operation: applicable classification test, platform's
declared posture, evidence supporting or undermining the posture,
pending classification disputes (state AG, NLRB, class actions).

## Coverage Stack
Platform's coverage stack (commercial GL, commercial auto / TNC, EPLI,
occupational-accident, contingent-WC, hired/non-owned auto). Map each
to which workforce segment and which platform-on / platform-off state.

## Personal-Policy Intersection
The seam between worker personal policies and platform coverage during
platform-on time. Document commercial-use exclusions in worker personal
policies and bridge / endorsement availability.

## Regulatory Posture
State-by-state regulatory mix: TNC statute, classification statute,
state AG position, state DOL audit posture, pending NLRB joint-employer
determinations.

## Proposed Bind / Decision
Bind terms or coverage call being submitted for review. Trace it back
to the classification posture, coverage-stack analysis, and regulatory
posture.

## Class-Action / Retroactive Exposure
Pending or signalled class-action / collective-action exposure that
would, if successful, retroactively reclassify workers and trigger
coverage exposure.

## Next Actions
Platform-disclosure refresh, worker onboarding-time coverage education,
state-AG monitoring, NLRB / DOL audit-readiness, telemetry-evidence
preservation.

## Evidence Gaps
Information missing from the inputs that materially affects the analysis.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this gig-platform liability analysis. Address EVERY issue in the
reviewer's critique, especially any CLASSIFICATION FLAGS,
COVERAGE-GAP FLAGS, or REGULATORY-PATCHWORK FLAGS.

PREVIOUS ANALYSIS:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any CLASSIFICATION FLAG: re-test the platform's operating model
against the state-specific test (AB5 ABC / IRS 20-factor / state-TNC
carve-out); state the test and the result.
⚠️  For any COVERAGE-GAP FLAG: name the specific seam between personal
and platform coverage and the bridge endorsement that closes it.
⚠️  For any REGULATORY-PATCHWORK FLAG: name the missing state regime and
the rule it imposes.
"""


@dataclass
class GigPlatformLiabilityRequest:
    """Structured input for the P&C gig-platform-liability workflow."""

    platform_summary: str
    """Platform name, business model, service type (rideshare / delivery /
    skilled-trades / on-demand-services), state(s) of operation, worker
    count, revenue tier."""

    workforce_classification: str
    """Worker mix (1099 / W-2 / contested); the classification posture the
    platform takes by state; any pending classification disputes."""

    coverage_stack: str
    """Existing coverage stack: commercial GL, commercial auto / TNC,
    EPLI, occupational-accident, contingent-WC, hired/non-owned auto;
    sub-limits and trigger definitions."""

    personal_policy_context: str
    """Worker personal-policy posture: commercial-use exclusions in
    personal auto / homeowners; bridge endorsement availability; platform-
    on / platform-off definition relative to app telemetry."""

    state_regulatory_posture: str
    """State-by-state regulatory mix: applicable TNC statute,
    classification statute, state AG position, state DOL audit posture,
    NLRB joint-employer status."""

    pending_litigation: str
    """Class-action / collective-action signals, state AG investigations,
    DOL audits, NLRB charges; pending or recently-settled matters."""

    proposed_bind_or_decision: str
    """Bind terms or coverage call submitted for review."""

    def to_prompt_text(self) -> str:
        return "\n".join([
            f"Platform summary: {self.platform_summary}",
            f"Workforce classification: {self.workforce_classification}",
            f"Coverage stack: {self.coverage_stack}",
            f"Personal-policy context: {self.personal_policy_context}",
            f"State regulatory posture: {self.state_regulatory_posture}",
            f"Pending litigation: {self.pending_litigation}",
            f"Proposed bind / decision: {self.proposed_bind_or_decision}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "CLASSIFICATION FLAGS:",
    "COVERAGE-GAP FLAGS:",
    "REGULATORY-PATCHWORK FLAGS:",
)


class GigPlatformLiabilityWorkflow(BaseWorkflow):
    """
    Adversarial gig-platform liability analysis: executor drafts bind /
    coverage call → reviewer challenges worker-classification posture,
    personal-vs-platform coverage seams, and state-regulatory patchwork,
    with the power to VETO → iterate.

    Convergence gate (D-PC-4):
        score ≥ threshold
        AND zero CLASSIFICATION FLAGS
        AND zero COVERAGE-GAP FLAGS
        AND zero REGULATORY-PATCHWORK FLAGS
        AND no REVIEWER VETO
    """

    async def run(  # type: ignore[override]
        self,
        request: GigPlatformLiabilityRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial gig-platform-liability loop."""
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
                criteria=_GIG_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            # Audit-trail writes happen BEFORE the veto check.
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

        counsel_checklist = self._build_counsel_checklist(
            request, accumulated, veto_reason
        )

        output_with_banners = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "platform_summary": request.platform_summary,
            "classification_flags": list(dict.fromkeys(accumulated["CLASSIFICATION FLAGS:"])),
            "coverage_gap_flags": list(dict.fromkeys(accumulated["COVERAGE-GAP FLAGS:"])),
            "regulatory_patchwork_flags": list(
                dict.fromkeys(accumulated["REGULATORY-PATCHWORK FLAGS:"])
            ),
            "counsel_checklist": counsel_checklist,
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
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "CLASSIFICATION FLAGS:": (
                "⚠️  CLASSIFICATION FLAGS (re-test platform's operating model against "
                "state-specific classification rule; state the result):"
            ),
            "COVERAGE-GAP FLAGS:": (
                "⚠️  COVERAGE-GAP FLAGS (name the specific seam between personal "
                "and platform coverage and the bridging endorsement that closes it):"
            ),
            "REGULATORY-PATCHWORK FLAGS:": (
                "⚠️  REGULATORY-PATCHWORK FLAGS (name the missing state regime "
                "and the rule it imposes):"
            ),
        }
        parts: list[str] = []
        for header in _FLAG_HEADERS:
            flags = current[header]
            if not flags:
                continue
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}" for f in flags
            )
            parts.append(f"{banner[header]}\n{flags_text}")
        return "\n" + "\n".join(parts) + "\n"

    @staticmethod
    def _compose_output(draft: str, veto_reason: str | None) -> str:
        if veto_reason is None:
            return f"{draft}\n\n---\n\n{_DISCLAIMER}"
        return f"{draft}\n\n---\n\n{_VETO_BANNER}\n\n{_DISCLAIMER}"

    @staticmethod
    def _build_counsel_checklist(
        request: GigPlatformLiabilityRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = []
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — escalate to platform-liability counsel "
                "BEFORE any bind or communication"
            )
        if accumulated["CLASSIFICATION FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  CLASSIFICATION FLAGS "
                f"({len(accumulated['CLASSIFICATION FLAGS:'])}) — re-test against "
                "state-specific classification rule; verify platform's operating model"
            )
        if accumulated["COVERAGE-GAP FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  COVERAGE-GAP FLAGS "
                f"({len(accumulated['COVERAGE-GAP FLAGS:'])}) — schedule bridge "
                "endorsements before bind"
            )
        if accumulated["REGULATORY-PATCHWORK FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  REGULATORY-PATCHWORK FLAGS "
                f"({len(accumulated['REGULATORY-PATCHWORK FLAGS:'])}) — add missing "
                "state regime treatment"
            )
        checklist.extend([
            "[ ] Confirm platform-app telemetry definition of platform-on / platform-off",
            "[ ] Worker-classification audit-readiness review (NLRB / DOL / state AG)",
            "[ ] Personal-policy bridge endorsement availability check by state",
            "[ ] Occupational-accident vs state-WC substitution validity check by state",
            f"[ ] Multi-state operations sanity: {request.platform_summary[:60]}",
            "[ ] Pending-litigation class-rep / reclassification exposure pricing",
            "[ ] Bind decision — AI output must not trigger automated issuance",
        ])
        return checklist
