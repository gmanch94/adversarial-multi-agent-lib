"""
Workflow — CGT Post-Change Comparability Review (Lifesciences · Advanced
Therapies / CGT, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to a manufacturing
change (process, site, vector lot, scale) for a living cell or gene therapy:
executor argues the post-change product is comparable to the pre-change product;
reviewer (cross-model per ARIS §2.1) challenges a change that affects a critical
quality attribute, an analytical package insufficient to conclude comparability,
and residual uncertainty needing clinical bridging, with the power to VETO when
the product is not demonstrably comparable and would ship as a materially
different product without the required clinical data.

Boundary (D-LIFESCI-2): distinct from BiosimilarComparabilityWorkflow, which
assesses a well-characterised recombinant-protein analytical-similarity exercise.
This assesses a living cell / viral-vector product with small patient-specific
autologous lots.

Veto gate (D-LIFESCI-8): fires when the post-change product is not demonstrably
comparable — the change affects a critical quality attribute the package does not
cover — such that treating it as comparable would ship a materially different
product without the required new clinical data.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Process-historian + batch-record system — pre/post process data should
       resolve against the controlled batch records, not caller-pasted summaries.
    2. Analytical-characterisation database — the comparability panel should read
       controlled characterisation data with methods and acceptance ranges.
    3. Stability database — post-change stability should reconcile against the
       controlled stability database.
    4. Comparability-protocol repository — the change should map to a
       pre-approved comparability protocol where one exists.
    5. Qualified approver gate — every AI-suggested comparability conclusion must
       be confirmed by a qualified Regulatory Affairs + CMC reviewer. Output is
       never a filed comparability determination.
    6. Dedicated third-model comparability auditor — production should use a
       separately configured auditor model for comparability-inflation bias
       detection. See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import (
    extract_flags,
    extract_veto_directive,
    sanitize_for_prompt,
    sanitize_request_text,
    truncate_flag_display,
)
from ...core.workflow import BaseWorkflow, WorkflowResult

_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "ADVISORY ONLY — This AI-generated post-change comparability review is "
    "decision-support, not a comparability determination and not a regulatory "
    "submission. A qualified Regulatory Affairs + CMC reviewer must independently "
    "confirm the analytical and clinical comparability case before any change is "
    "implemented. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found the "
    "post-change product not demonstrably comparable — the change affects a "
    "critical quality attribute the package does not cover; treating it as "
    "comparable would ship a materially different product without the required "
    "clinical data. See metadata['veto_reason']. Escalate to Regulatory Affairs + CMC."
)

_FLAG_HEADERS = ("PROCESS-DELTA FLAGS:", "ANALYTICAL-GAP FLAGS:", "CLINICAL-BRIDGE FLAGS:")

_COMPARABILITY_REVIEW_CRITERIA = """\
Evaluate this post-change comparability review on five dimensions. Score each 0–10.

1. PROCESS-CHANGE IMPACT (30%) — CRITICAL
   Does the change (process, site, vector lot, scale) plausibly affect a critical
   quality attribute? Penalise a change whose impact on a CQA is not addressed.
   Flag under PROCESS-DELTA FLAGS:.

2. ANALYTICAL COMPARABILITY COVERAGE (25%) — CRITICAL
   Is the analytical panel sufficient (right attributes, right stage, adequately
   powered) to conclude comparability? Penalise a panel that cannot support the
   conclusion. Flag under ANALYTICAL-GAP FLAGS:.

3. CLINICAL BRIDGING SUFFICIENCY (20%) — CRITICAL
   Where residual uncertainty remains, does the clinical bridging plan address it?
   Penalise residual uncertainty with no clinical bridge. Flag under
   CLINICAL-BRIDGE FLAGS:.

4. RISK ASSESSMENT (15%)
   Does the risk assessment identify and rank the change's quality risks
   correctly? Penalise an understated risk assessment.

5. ACTIONABILITY (10%)
   Is each finding specific enough for CMC to resolve (which attribute, which
   method, which study)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the post-change product is not demonstrably comparable — the change
affects a critical quality attribute the package does not cover — such that
treating it as comparable would ship a materially different product without the
required new clinical data.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero PROCESS-DELTA FLAGS AND zero ANALYTICAL-GAP FLAGS AND zero
CLINICAL-BRIDGE FLAGS AND no VETO: ready for Regulatory Affairs + CMC sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PROCESS-DELTA FLAGS: [bullet list, or "None detected"]
  ANALYTICAL-GAP FLAGS: [bullet list, or "None detected"]
  CLINICAL-BRIDGE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are reviewing a manufacturing change for a living cell or gene therapy for a
qualified Regulatory Affairs + CMC reviewer. You have no stake in the outcome.
Assess whether the post-change product is comparable to the pre-change product, or
whether the change makes it a materially different product needing new clinical
data, grounded only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

COMPARABILITY DATA:
{request_text}

{wiki_context}

Produce a structured review with exactly these sections:

## Process-change impact
State whether the change plausibly affects a critical quality attribute; identify
any CQA impact not addressed.

## Analytical comparability
State whether the analytical panel is sufficient to conclude comparability;
identify any gap.

## Clinical bridging
State whether residual uncertainty is addressed by the clinical bridging plan.

## Risk assessment
State whether the risk assessment identifies and ranks the change's quality risks.

## Comparability conclusion
State whether the post-change product is comparable, or whether it is a materially
different product needing new clinical data.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this post-change comparability review. Address EVERY issue in the
reviewer's critique, especially any PROCESS-DELTA FLAGS, ANALYTICAL-GAP FLAGS, or
CLINICAL-BRIDGE FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any PROCESS-DELTA flag: address the change's impact on the named critical
quality attribute, or acknowledge it is uncovered.
⚠️  For any ANALYTICAL-GAP flag: extend the analytical panel to support the
comparability conclusion, or acknowledge the gap.
⚠️  For any CLINICAL-BRIDGE flag: provide the clinical bridging that resolves the
residual uncertainty, or acknowledge new clinical data are required.
"""


@dataclass
class ComparabilityRequest:
    """Structured input for the CGT post-change comparability review workflow."""

    product_description: str
    """Generic product category (e.g. an autologous gene-modified cell therapy)."""

    change_description: str
    """The manufacturing change: process / site / vector-lot / scale."""

    pre_change_process_summary: str
    """Pre-change process summary."""

    post_change_process_summary: str
    """Post-change process summary."""

    analytical_comparability_data: str
    """Analytical comparability data across the quality-attribute panel."""

    quality_attribute_panel: str
    """The quality-attribute panel (identity, purity, potency, safety)."""

    clinical_bridging_plan: str
    """Clinical bridging plan for any residual uncertainty."""

    risk_assessment_summary: str
    """Risk assessment for the change."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Change description: {self.change_description[:cap]}",
            f"Pre-change process summary: {self.pre_change_process_summary[:cap]}",
            f"Post-change process summary: {self.post_change_process_summary[:cap]}",
            f"Analytical comparability data: {self.analytical_comparability_data[:cap]}",
            f"Quality-attribute panel: {self.quality_attribute_panel[:cap]}",
            f"Clinical bridging plan: {self.clinical_bridging_plan[:cap]}",
            f"Risk assessment summary: {self.risk_assessment_summary[:cap]}",
        ])


class CGTComparabilityWorkflow(BaseWorkflow):
    """
    Adversarial CGT post-change comparability review: executor argues comparability
    → reviewer challenges an uncovered CQA impact, an insufficient analytical
    package, and residual uncertainty needing clinical bridging, with the power to
    VETO → iterate.

    Convergence gate (D-LIFESCI-8):
        score ≥ threshold (8.0)
        AND zero PROCESS-DELTA FLAGS
        AND zero ANALYTICAL-GAP FLAGS
        AND zero CLINICAL-BRIDGE FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the wiki.
    The verbatim veto directive is recorded in metadata['veto_reason'];
    metadata['first_draft'] captures the clean executor draft from the vetoed round.
    """

    async def run(  # type: ignore[override]
        self,
        request: ComparabilityRequest,
        **_: Any,
    ) -> WorkflowResult:
        config = self.config
        request_text = sanitize_request_text(request)
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
                criteria=_COMPARABILITY_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
                round_num=round_num,
                score=score,
            )

            veto_reason = self._extract_veto(review.critique, max_wiki_chars)
            if veto_reason is not None:
                break

            if review.approved and not self._flag_classes_unresolved(
                review.critique, _FLAG_HEADERS, current.values()
            ):
                converged = True
                break

        comparability_checklist = self._build_comparability_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "product_description": sanitize_for_prompt(
                request.product_description, max_chars=200
            ),
            "process_delta_flags": list(dict.fromkeys(accumulated["PROCESS-DELTA FLAGS:"])),
            "analytical_gap_flags": list(dict.fromkeys(accumulated["ANALYTICAL-GAP FLAGS:"])),
            "clinical_bridge_flags": list(dict.fromkeys(accumulated["CLINICAL-BRIDGE FLAGS:"])),
            "comparability_checklist": comparability_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
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
        """Thin delegate to `core._internal.extract_veto_directive` (M-PC-1)."""
        return extract_veto_directive(critique, "REVIEWER VETO:", max_chars)

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "PROCESS-DELTA FLAGS:": (
                "⚠️  PROCESS-DELTA FLAGS (address the change's impact on the named "
                "critical quality attribute, or acknowledge it is uncovered):"
            ),
            "ANALYTICAL-GAP FLAGS:": (
                "⚠️  ANALYTICAL-GAP FLAGS (extend the analytical panel to support the "
                "comparability conclusion, or acknowledge the gap):"
            ),
            "CLINICAL-BRIDGE FLAGS:": (
                "⚠️  CLINICAL-BRIDGE FLAGS (provide the clinical bridging that resolves "
                "the residual uncertainty, or acknowledge new clinical data required):"
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
    def _build_comparability_checklist(
        request: ComparabilityRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Regulatory Affairs + CMC Lead]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — do not treat the product as comparable; "
                "escalate to Regulatory Affairs + CMC and generate the required new "
                "clinical data before implementing the change"
            )
        process_flags = accumulated.get("PROCESS-DELTA FLAGS:", [])
        analytical_flags = accumulated.get("ANALYTICAL-GAP FLAGS:", [])
        bridge_flags = accumulated.get("CLINICAL-BRIDGE FLAGS:", [])
        if process_flags:
            checklist.append(
                f"[ ] ⚠️  PROCESS-DELTA FLAGS ({len(process_flags)}) — address the "
                "change's impact on each flagged critical quality attribute"
            )
        if analytical_flags:
            checklist.append(
                f"[ ] ⚠️  ANALYTICAL-GAP FLAGS ({len(analytical_flags)}) — extend the "
                "analytical panel to support comparability"
            )
        if bridge_flags:
            checklist.append(
                f"[ ] ⚠️  CLINICAL-BRIDGE FLAGS ({len(bridge_flags)}) — provide the "
                "clinical bridging for each residual uncertainty"
            )
        checklist.extend([
            "[ ] Confirm every critical quality attribute affected by the change is covered",
            "[ ] Confirm the analytical panel supports the comparability conclusion",
            "[ ] Confirm residual uncertainty is bridged clinically or new data are planned",
            "[ ] Obtain Regulatory Affairs + CMC sign-off before implementing the change",
        ])
        return checklist
