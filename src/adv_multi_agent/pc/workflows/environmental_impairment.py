"""
Workflow — Environmental Impairment Liability (Specialty P&C Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to specialty
environmental underwriting / claims (Pollution Legal Liability,
Contractors Pollution Liability, site-specific Environmental Impairment).

This is the **specialty-lines** track of the P&C domain (see D-PC-6):
long-tail risks with EPA / CERCLA / state-DEP regulatory overlap, where
prior-knowledge and known-condition disputes are the dominant loss
driver and where reserve / coverage decisions are highly path-dependent.

Triple-flag gate (D-PC-4) + **reviewer-veto**: prior-knowledge / known-
condition findings on a PLL form trigger an immediate veto regardless of
score — the policy form excludes those losses by design and proceeding
without escalation creates bad-faith exposure.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Authoritative regulator-feed integration — EPA ECHO, RCRAInfo,
       NPL/CERCLA database, state DEP records are all structured feeds;
       production retrieval must be authoritative, not paraphrased.
    2. Phase I / Phase II ESA data — site_history is free-text;
       production requires structured Phase I ESA + Phase II analytical
       results parsing.
    3. Long-tail reserve development — environmental tail is uniquely
       long (10–30+ years); production must integrate company-specific
       development triangles, not LLM intuition.
    4. Coverage trigger doctrine — exposure / manifestation / continuous-
       trigger doctrines vary by state; production needs a structured
       state-by-state rule base.
    5. Co-insurer / historical-policy archaeology — environmental claims
       often span multiple policy years and carriers; production needs
       a structured policy-history database for allocation.
    6. Append-only audit store + dedicated third-model auditor — see
       ARIS §3.1.
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

# L-PC-3: per-field cap (see claims_reserve.py for rationale).
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated environmental analysis is not "
    "an authorised coverage / reserve decision. A credentialed "
    "environmental underwriter or claims specialist must verify site "
    "history, regulator status, and coverage-trigger doctrine before any "
    "decision is communicated. AI output must never trigger an automated "
    "denial or reserve booking."
)

_VETO_BANNER = (
    "⚠️  REVIEWER VETO — workflow halted before convergence. "
    "See metadata['veto_reason']. Escalate to environmental claims counsel "
    "and senior underwriter immediately; do not communicate this analysis."
)

_ENV_REVIEW_CRITERIA = """\
Evaluate this environmental analysis on four dimensions. Score each 0–10.

1. KNOWN-CONDITION FIDELITY (35%) — CRITICAL
   Has every documented historical use, regulator filing, and prior
   environmental event been mapped against the PLL / CPL policy form's
   known-condition / prior-knowledge exclusion? Are Phase I ESA
   recognized environmental conditions (RECs) addressed? Are CERCLA /
   state Superfund listings disclosed and properly characterised? Flag
   every known-condition gap under KNOWN-CONDITION FLAGS:.

2. TAIL & TRIGGER (30%) — CRITICAL
   Is the coverage-trigger doctrine for the governing state correctly
   identified (exposure / manifestation / continuous-trigger / injury-in-
   fact)? Is the long-tail development (10–30 yrs) reflected in any
   reserve discussion? Is the policy-period attribution defensible
   against other carriers on the risk? Flag every tail / trigger gap
   under TAIL FLAGS:.

3. REGULATORY OVERLAP (25%) — CRITICAL
   Does the analysis address all applicable regulator regimes (EPA,
   state DEP, CERCLA, RCRA, OPA-90, TSCA, applicable state Superfund
   statute, Brownfields agreements)? Are regulator-driven cost components
   (compelled investigation, oversight cost, natural-resource damages,
   mandated public participation) addressed? Flag every regulator-overlap
   gap under REGULATORY-OVERLAP FLAGS:.

4. ACTIONABILITY (10%)
   Are next-step recommendations (Phase II scoping, regulator outreach
   sequencing, co-insurer notification) specific enough for the claims
   handler or underwriter to execute?

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • The site_history reveals a documented prior environmental event,
    regulator filing, or recognized environmental condition (REC) that
    materially overlaps the claimed loss AND the policy form excludes
    known conditions — proceeding without escalation creates bad-faith
    exposure on the coverage call.
  • The site is on the National Priorities List (NPL) / state Superfund
    list AND the analysis treats it as unknown background.
  • The analysis proposes a denial AND a reasonable interpretation of the
    pollution event-trigger or sudden-and-accidental carve-out supports
    coverage in the governing state.
  • Co-insurer notification is required AND analysis treats the matter as
    single-policy.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto directive continuation line with
"Overall", "Key issues", or a markdown header (#) — those markers terminate
the veto block in the parser.

Overall score = weighted average.
Score ≥ 7.5 AND zero KNOWN-CONDITION FLAGS AND zero TAIL FLAGS AND zero
REGULATORY-OVERLAP FLAGS AND no VETO: analysis is ready for environmental
counsel review.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  KNOWN-CONDITION FLAGS: [bullet list, or "None detected"]
  TAIL FLAGS: [bullet list, or "None detected"]
  REGULATORY-OVERLAP FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are preparing an environmental coverage / reserve analysis for
environmental counsel and a senior environmental underwriter to review.
You have no stake in the outcome. Your job is to map site history to the
policy form's known-condition exclusion, identify the correct coverage-
trigger doctrine, and surface the regulator overlap — not to maximise
denial, not to maximise coverage.

BASE THE ANALYSIS ON THE INPUT DATA.

ENVIRONMENTAL DATA:
{request_text}

{wiki_context}

Produce a structured analysis with exactly these sections:

## Site & Loss Summary
Restate the site, operation, claimed loss / pollution condition, and date
of discovery in one paragraph.

## Site History & Known Conditions
Map every documented prior use, regulator filing, ESA finding (Phase I /
II), and recognized environmental condition (REC) against the policy
form's known-condition / prior-knowledge exclusion.

## Coverage Trigger
Identify the governing-state coverage-trigger doctrine (exposure /
manifestation / continuous-trigger / injury-in-fact). State how it
applies to the loss timeline.

## Policy-Period Attribution
For long-tail loss, attribute the loss across applicable policy periods
and carriers. Identify co-insurers if any.

## Regulatory Overlap
Address each applicable regime: EPA (CERCLA, RCRA, TSCA, OPA-90), state
DEP, state Superfund, Brownfields agreement. Identify regulator-driven
cost components.

## Coverage Conclusion / Reserve Recommendation
State the proposed call (cover / partial / deny) and / or the reserve
indication. Trace it to the known-condition analysis, trigger doctrine,
and regulator status.

## Next Actions
Phase II scoping, regulator outreach, co-insurer notification, counsel
engagement, NRD evaluation.

## Evidence Gaps
Information missing from the inputs that materially affects the analysis.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this environmental analysis. Address EVERY issue in the reviewer's
critique, especially any KNOWN-CONDITION FLAGS, TAIL FLAGS, or
REGULATORY-OVERLAP FLAGS.

PREVIOUS ANALYSIS:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any KNOWN-CONDITION FLAG: re-map the site history fact to the
exact known-condition / prior-knowledge clause; do not paper over the
exposure.
⚠️  For any TAIL FLAG: restate the trigger doctrine and policy-period
attribution with the development tail accounted for.
⚠️  For any REGULATORY-OVERLAP FLAG: name the regulator regime and the
required component (oversight cost, NRD, mandated public participation)
that was missed.
"""


@dataclass
class EnvironmentalImpairmentRequest:
    """Structured input for the P&C environmental-impairment workflow."""

    site_summary: str
    """Site location, current operation, ownership history (relevant span)."""

    site_history: str
    """Documented prior uses, regulator filings, Phase I / II ESA findings,
    recognized environmental conditions (RECs)."""

    pollution_condition: str
    """The discovered or alleged pollution condition: contaminants of
    concern, media (soil / groundwater / surface water / air), extent,
    date of discovery."""

    policy_form: str
    """PLL / CPL / EIL form citation; key clauses: insuring agreement,
    known-condition / prior-knowledge exclusion, retroactive date, claim-
    series clause, retention/SIR, sub-limits."""

    governing_state: str
    """State + coverage-trigger doctrine recognised in that state's case
    law."""

    regulator_status: str
    """EPA / state DEP / CERCLA / RCRA / OPA-90 status; NPL or state
    Superfund listing; consent orders; Brownfields agreements."""

    co_insurer_history: str
    """Policy-period chain of carriers (relevant for long-tail allocation);
    'Single carrier' if the loss falls in a single policy period."""

    proposed_decision_or_reserve: str
    """Proposed coverage call OR reserve indication being submitted for
    review."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Site summary: {self.site_summary[:cap]}",
            f"Site history: {self.site_history[:cap]}",
            f"Pollution condition: {self.pollution_condition[:cap]}",
            f"Policy form: {self.policy_form[:cap]}",
            f"Governing state: {self.governing_state[:cap]}",
            f"Regulator status: {self.regulator_status[:cap]}",
            f"Co-insurer history: {self.co_insurer_history[:cap]}",
            f"Proposed decision / reserve: {self.proposed_decision_or_reserve[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "KNOWN-CONDITION FLAGS:",
    "TAIL FLAGS:",
    "REGULATORY-OVERLAP FLAGS:",
)


class EnvironmentalImpairmentWorkflow(BaseWorkflow):
    """
    Adversarial environmental-impairment analysis: executor drafts
    coverage / reserve call → reviewer challenges known-condition mapping,
    trigger doctrine, and regulator overlap, with the power to VETO →
    iterate.

    Convergence gate (D-PC-4):
        score ≥ threshold
        AND zero KNOWN-CONDITION FLAGS
        AND zero TAIL FLAGS
        AND zero REGULATORY-OVERLAP FLAGS
        AND no REVIEWER VETO
    """

    async def run(  # type: ignore[override]
        self,
        request: EnvironmentalImpairmentRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial environmental-impairment loop."""
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
                criteria=_ENV_REVIEW_CRITERIA,
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
            "site_summary": request.site_summary,
            "known_condition_flags": list(dict.fromkeys(accumulated["KNOWN-CONDITION FLAGS:"])),
            "tail_flags": list(dict.fromkeys(accumulated["TAIL FLAGS:"])),
            "regulatory_overlap_flags": list(dict.fromkeys(accumulated["REGULATORY-OVERLAP FLAGS:"])),
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
            "KNOWN-CONDITION FLAGS:": (
                "⚠️  KNOWN-CONDITION FLAGS (map the site-history fact to the exact "
                "known-condition / prior-knowledge clause):"
            ),
            "TAIL FLAGS:": (
                "⚠️  TAIL FLAGS (restate the trigger doctrine and policy-period "
                "attribution with the long development tail accounted for):"
            ),
            "REGULATORY-OVERLAP FLAGS:": (
                "⚠️  REGULATORY-OVERLAP FLAGS (name the regulator regime and the "
                "missed regulator-driven cost component):"
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
        return f"{draft}\n\n---\n\n{_VETO_BANNER}\n\n{_DISCLAIMER}"

    @staticmethod
    def _build_counsel_checklist(
        request: EnvironmentalImpairmentRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = []
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — escalate to environmental claims counsel "
                "BEFORE any communication to the insured"
            )
        if accumulated["KNOWN-CONDITION FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  KNOWN-CONDITION FLAGS "
                f"({len(accumulated['KNOWN-CONDITION FLAGS:'])}) — pull Phase I/II "
                "ESA and prior regulator correspondence; re-map to known-condition clause"
            )
        if accumulated["TAIL FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  TAIL FLAGS ({len(accumulated['TAIL FLAGS:'])}) — confirm "
                "trigger doctrine for governing state; re-do policy-period allocation"
            )
        if accumulated["REGULATORY-OVERLAP FLAGS:"]:
            checklist.append(
                f"[ ] ⚠️  REGULATORY-OVERLAP FLAGS "
                f"({len(accumulated['REGULATORY-OVERLAP FLAGS:'])}) — confirm EPA / "
                "state DEP / CERCLA status; engage regulator-liaison counsel"
            )
        checklist.extend([
            "[ ] Pull Phase I ESA + Phase II analytical results (authoritative)",
            "[ ] Confirm NPL / state Superfund status against authoritative regulator feed",
            f"[ ] Confirm coverage-trigger doctrine for: {request.governing_state[:50]}",
            "[ ] Co-insurer notification per policy-period chain (if multi-period loss)",
            "[ ] Natural Resource Damages (NRD) exposure evaluation if surface water / wildlife implicated",
            "[ ] Environmental counsel review before any coverage communication",
            "[ ] Issue decision / book reserve — AI output must not trigger automatic action",
        ])
        return checklist
