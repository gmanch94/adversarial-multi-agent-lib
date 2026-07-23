"""
Workflow — Recall Scope Manufacturing (Industrial Manufacturing Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to industrial-
equipment recall scope determination — the regulator-defensible decision
of which serial numbers, which build dates, and which configurations are
covered by a recall or service action.

Mirrors `retail.recall_scope.RecallScopeWorkflow` structure (D-RETAIL-1
veto pattern); the industrial analog adds CPSC § 15(b) substantial-
product-hazard mapping, OSHA-recordable correlation, and treaty-reinsurer
notification triggers.

Executor drafts a recall scope; reviewer (recommended: different model
family per ARIS §2.1 principle 1) challenges narrow scoping (the most
common life-safety failure), missing regulator notifications, and weak
trigger evidence, and can issue a REVIEWER VETO when life-safety
exposure exists but scope is under-drawn.

Veto + triple-flag gate (D-IND-1): TRIGGER-EVIDENCE FLAGS, FLEET-SCOPE
FLAGS, REGULATORY-NOTIFY FLAGS, plus **reviewer veto**.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PLM / ERP serial-traceability — fleet-scope determination requires
       structured serial-number / lot / build-date traceability against
       BOM revisions, not caller-supplied prose.
    2. CMMS / FRACAS / customer-quality-feedback — field-failure population
       data for the substantial-product-hazard analysis must come from a
       structured failure-reporting system.
    3. Regulator notification engine — CPSC § 15(b) substantial-product-
       hazard reports, OSHA notification, NHTSA-equivalent (where
       applicable), EU RAPEX / Safety Gate, and state AG notifications
       all require structured submission, not checklist line items.
    4. Reinsurer / product-liability notice — recall above retention
       triggers structured cession notice, not checklist line item.
    5. Service-bulletin and parts-availability — retrofit instructions,
       parts SKUs, service-network capacity all need structured workflow
       integration.
    6. Append-only audit store — every draft, flag, and veto must be
       captured in a tamper-evident store defensible against CPSC,
       OSHA, and product-liability discovery.
    7. Dedicated third-model safety auditor — see ARIS §3.1.
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
    "⚠️  ADVISORY ONLY — This AI-generated recall scope is not an "
    "authorised recall decision or regulator notification. A credentialed "
    "product-safety committee, in-house counsel, and (where applicable) "
    "outside regulatory counsel must verify scope, trigger evidence, and "
    "notification obligations before any recall is initiated or "
    "regulator notice is filed. AI output must never trigger an "
    "automated recall initiation or regulator filing."
)

_VETO_BANNER = (
    "⚠️  REVIEWER VETO — workflow halted before convergence. "
    "See metadata['veto_reason']. Escalate to product-safety committee + "
    "in-house counsel + outside regulatory counsel IMMEDIATELY; "
    "life-safety exposure may be under-scoped or regulator notification "
    "obligations may be unmet."
)

_RECALL_REVIEW_CRITERIA = """\
Evaluate this recall scope on four dimensions. Score each 0–10.

1. TRIGGER EVIDENCE INTEGRITY (35%) — CRITICAL
   Is the trigger evidence (field-failure population, CMMS records,
   customer complaints, telematics anomalies, regulator inquiry) credible
   and quantified? Does it support a substantial-product-hazard finding
   under CPSC § 15(b)? Penalise trigger evidence that is anecdotal,
   single-source, or under-quantified. Flag every gap under TRIGGER-
   EVIDENCE FLAGS:.

2. FLEET-SCOPE COMPLETENESS (30%) — CRITICAL
   Does the scope cover all serial numbers / lots / build dates / option
   configurations exposed to the failure mode? Are adjacent products
   sharing the same component included? Are pre-production / engineering
   builds addressed? Penalise narrow scope that misses adjacent
   exposure. Flag every gap under FLEET-SCOPE FLAGS:.

3. REGULATORY NOTIFICATION (25%) — CRITICAL
   Are all applicable regulator notifications identified — CPSC § 15(b),
   OSHA, NHTSA-equivalent (if road-going), EU RAPEX / Safety Gate, state
   AG, country-specific where exported? Are the 24-hour / 5-day reporting
   clocks respected? Penalise missing notifications. Flag every gap under
   REGULATORY-NOTIFY FLAGS:.

4. ACTIONABILITY (10%)
   Are the next actions (service-bulletin draft, parts availability,
   service-network capacity, customer communication plan, reinsurer
   notice, dealer training) specific enough for the recall coordinator
   to execute?

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Substantial-product-hazard signal is present (death / serious injury
    or risk of either, OR violation of mandatory safety standard) but
    scope is drawn narrowly or notification timing is missed.
  • Field-failure population shows a non-random spatial / temporal pattern
    but the scope excludes serials in the affected band.
  • Adjacent products share the failure-mode-bearing component but are
    excluded from scope.
  • A regulator's published reportable-hazard criterion is met but the
    notification is not in the next-actions list.
  • CPSC § 15(b) "becomes aware" trigger is met but the 5-business-day
    reporting clock is not addressed.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto directive continuation line with
"Overall", "Key issues", or a markdown header (#) — those markers terminate
the veto block in the parser.

Overall score = weighted average.
Score ≥ 7.5 AND zero TRIGGER-EVIDENCE FLAGS AND zero FLEET-SCOPE FLAGS AND
zero REGULATORY-NOTIFY FLAGS AND no VETO: recall scope is ready for
product-safety review. Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  TRIGGER-EVIDENCE FLAGS: [bullet list, or "None detected"]
  FLEET-SCOPE FLAGS: [bullet list, or "None detected"]
  REGULATORY-NOTIFY FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are preparing a recall scope for an industrial OEM's product-safety
committee. You have no stake in the outcome. Your job is to draw scope at
the level that covers every exposed unit and meets every applicable
regulator notification — not to minimise commercial impact, not to
inflate scope for cautious defaults.

BASE THE SCOPE ON THE INPUT DATA.

RECALL DATA:
{request_text}

{wiki_context}

Produce a structured recall scope with exactly these sections:

## Trigger and Hazard Summary
Restate the triggering signal: field failure mode, severity, population
statistics, regulator inquiry status. Map to CPSC § 15(b) substantial-
product-hazard tier (death/serious-injury / unreasonable risk / standard
non-compliance).

## Evidence Inventory
Field-failure population data, CMMS / FRACAS records, customer
complaints, telematics anomalies, engineering investigation status. Note
gaps explicitly.

## Fleet Scope
Serial-number / lot / build-date / configuration scope. Adjacent products
sharing the failure-mode-bearing component. Pre-production / engineering-
build exposure. International / export exposure.

## Regulatory Notifications
List every applicable notification: CPSC § 15(b), OSHA, NHTSA-equivalent
if road-going, EU RAPEX / Safety Gate, state AG, country-specific. State
the clock (24-hr / 5-business-day / immediate) and the addressee.

## Service Action Plan
Service-bulletin scope, retrofit instructions, parts availability,
service-network capacity, customer communication, dealer training.

## Reinsurance and Liability
Recall expense retention vs treaty, product-liability notice
implications, Insurance Services Office line of business.

## Recall Decision
Initiate / Investigate Further / No Action. State approving authority,
public-announcement plan, and reinsurer notice.

## Evidence Gaps
Information missing from the inputs that materially affects scope.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this recall scope. Address EVERY issue in the reviewer's critique,
especially any TRIGGER-EVIDENCE FLAGS, FLEET-SCOPE FLAGS, or
REGULATORY-NOTIFY FLAGS.

PREVIOUS SCOPE:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any TRIGGER-EVIDENCE FLAG: cite the failure-population statistics
or upgrade the evidence tier; do not handwave on substantial-product-
hazard analysis.
⚠️  For any FLEET-SCOPE FLAG: expand the serial-number / build-date band,
add adjacent products sharing the component, or state the explicit
exclusion basis.
⚠️  For any REGULATORY-NOTIFY FLAG: add the missing regulator notice with
the applicable reporting clock and addressee.
"""


@dataclass
class RecallScopeManufacturingRequest:
    """Structured input for the manufacturing recall-scope workflow."""

    trigger_summary: str
    """Triggering signal: failure mode, severity, population, regulator
    inquiry status, CPSC § 15(b) tier hypothesis."""

    evidence_inventory: str
    """Field-failure data, CMMS / FRACAS, complaints, telematics anomalies,
    engineering investigation."""

    fleet_serial_traceability: str
    """Serial / lot / build-date / configuration traceability for the
    affected component."""

    adjacent_product_exposure: str
    """Other products / platforms sharing the failure-mode-bearing component."""

    regulatory_context: str
    """Applicable regulators (CPSC, OSHA, NHTSA-equivalent, EU RAPEX,
    state AG, country-specific) and any active inquiry."""

    service_capacity_context: str
    """Service-network capacity, parts availability, retrofit complexity,
    dealer-training status."""

    proposed_scope: str
    """Investigator's first-pass scope (serials, action, communications) +
    reasoning."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Trigger summary: {self.trigger_summary[:cap]}",
            f"Evidence inventory: {self.evidence_inventory[:cap]}",
            f"Fleet serial traceability: {self.fleet_serial_traceability[:cap]}",
            f"Adjacent product exposure: {self.adjacent_product_exposure[:cap]}",
            f"Regulatory context: {self.regulatory_context[:cap]}",
            f"Service capacity context: {self.service_capacity_context[:cap]}",
            f"Proposed scope: {self.proposed_scope[:cap]}",
        ])


class RecallScopeManufacturingWorkflow(BaseWorkflow):
    """
    Adversarial recall-scope determination: executor drafts a scope →
    reviewer challenges trigger evidence, fleet-scope completeness, and
    regulator-notification coverage, with the power to VETO → iterate.

    Convergence gate (D-IND-1, mirroring D-RETAIL-1):
        score ≥ threshold
        AND zero TRIGGER-EVIDENCE FLAGS
        AND zero FLEET-SCOPE FLAGS
        AND zero REGULATORY-NOTIFY FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately, recording the verbatim veto
    directive in metadata['veto_reason']. Score and flags from the vetoed
    round are also captured.
    """

    async def run(  # type: ignore[override]
        self,
        request: RecallScopeManufacturingRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_trigger_flags: list[str] = []
        current_fleet_flags: list[str] = []
        current_regulatory_flags: list[str] = []
        all_trigger_flags: list[str] = []
        all_fleet_flags: list[str] = []
        all_regulatory_flags: list[str] = []
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
                    current_trigger_flags,
                    current_fleet_flags,
                    current_regulatory_flags,
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
                criteria=_RECALL_REVIEW_CRITERIA,
            )
            score = review.score
            current_trigger_flags = extract_flags(
                review.critique, "TRIGGER-EVIDENCE FLAGS:"
            )
            current_fleet_flags = extract_flags(review.critique, "FLEET-SCOPE FLAGS:")
            current_regulatory_flags = extract_flags(
                review.critique, "REGULATORY-NOTIFY FLAGS:"
            )
            all_trigger_flags.extend(current_trigger_flags)
            all_fleet_flags.extend(current_fleet_flags)
            all_regulatory_flags.extend(current_regulatory_flags)

            # Audit-trail writes happen BEFORE the veto check — CPSC
            # discovery defensibility requires the vetoed-round record.
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
                and not current_trigger_flags
                and not current_fleet_flags
                and not current_regulatory_flags
            ):
                converged = True
                break

        safety_checklist = self._build_safety_checklist(
            request,
            all_trigger_flags,
            all_fleet_flags,
            all_regulatory_flags,
            veto_reason,
        )

        output_with_banners = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "trigger_summary": sanitize_for_prompt(
                request.trigger_summary, max_chars=200
            ),
            "trigger_evidence_flags": list(dict.fromkeys(all_trigger_flags)),
            "fleet_scope_flags": list(dict.fromkeys(all_fleet_flags)),
            "regulatory_notify_flags": list(dict.fromkeys(all_regulatory_flags)),
            "safety_checklist": safety_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round
            # so the safety officer sees what the AI produced before the
            # REVIEWER VETO banner was prepended. Ledger + wiki also preserve
            # this, but metadata['first_draft'] makes it directly queryable.
            metadata["first_draft"] = output

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
        trigger_flags: list[str],
        fleet_flags: list[str],
        regulatory_flags: list[str],
    ) -> str:
        if not trigger_flags and not fleet_flags and not regulatory_flags:
            return ""
        parts: list[str] = []
        if trigger_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(trigger_flags)
            )
            parts.append(
                "⚠️  TRIGGER-EVIDENCE FLAGS (cite failure-population stats "
                "or upgrade evidence tier; do not handwave on SPH analysis):\n"
                f"{flags_text}"
            )
        if fleet_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(fleet_flags)
            )
            parts.append(
                "⚠️  FLEET-SCOPE FLAGS (expand serial / build-date band; add "
                "adjacent products sharing the component):\n"
                f"{flags_text}"
            )
        if regulatory_flags:
            flags_text = "\n".join(
                f"  - {sanitize_for_prompt(f, max_chars=500)}"
                for f in truncate_flag_display(regulatory_flags)
            )
            parts.append(
                "⚠️  REGULATORY-NOTIFY FLAGS (add missing notices with "
                "reporting clock and addressee):\n"
                f"{flags_text}"
            )
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
    def _build_safety_checklist(
        request: RecallScopeManufacturingRequest,
        trigger_flags: list[str],
        fleet_flags: list[str],
        regulatory_flags: list[str],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = []
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — escalate to product-safety committee + "
                "in-house counsel + outside regulatory counsel BEFORE initiation"
            )
        if trigger_flags:
            checklist.append(
                f"[ ] ⚠️  TRIGGER-EVIDENCE FLAGS ({len(trigger_flags)}) — "
                "quantify field-failure population; CPSC SPH tier analysis"
            )
        if fleet_flags:
            checklist.append(
                f"[ ] ⚠️  FLEET-SCOPE FLAGS ({len(fleet_flags)}) — "
                "re-pull serial / build-date / option band; add adjacent products"
            )
        if regulatory_flags:
            checklist.append(
                f"[ ] ⚠️  REGULATORY-NOTIFY FLAGS ({len(regulatory_flags)}) — "
                "verify CPSC § 15(b) 5-business-day + applicable jurisdictions"
            )
        checklist.extend([
            "[ ] Product-safety committee sign-off on scope + decision",
            "[ ] In-house counsel + outside regulatory counsel review",
            "[ ] CPSC § 15(b) report drafted and reviewed (if applicable)",
            "[ ] OSHA / NHTSA-equivalent / RAPEX / state AG notifications drafted",
            "[ ] Reinsurer / product-liability notice prepared if above retention",
            "[ ] Service-bulletin + retrofit-instructions + parts SKU ready",
            "[ ] Customer / dealer communication plan signed off",
            f"[ ] Confirm adjacent-product list: {request.adjacent_product_exposure[:60]}",
            "[ ] Initiate recall + file notices — AI output must not trigger automatic action",
        ])
        return checklist
