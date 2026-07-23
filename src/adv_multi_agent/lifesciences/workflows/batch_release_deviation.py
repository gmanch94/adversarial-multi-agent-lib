"""
Workflow — Batch Release Deviation Disposition (Lifesciences · Pharma, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to GMP batch-release
disposition: executor dispositions a batch carrying a manufacturing deviation
(criticality, CQA impact, release risk, disposition); reviewer (cross-model per
ARIS §2.1) challenges any under-classified criticality, incomplete impact
assessment, and unresolved release risk, with the power to VETO when a 'release'
disposition would put a non-conforming batch into distribution.

Veto gate (D-LIFESCI-4): fires when a 'release' disposition is proposed for a
batch with an unresolved critical deviation affecting a critical quality
attribute (CQA) or patient safety.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. MES / electronic batch record — the batch record and its deviations
       should resolve against the controlled MES/EBR, not caller-pasted text.
    2. Deviation / CAPA system — the deviation classification and CAPA state
       should reflect the controlled deviation-management system.
    3. Specification + CoA system — CQA impact should resolve against the
       controlled specification and certificate of analysis.
    4. QP release register — no batch is released except by the Qualified Person
       through the controlled release register; this workflow does not release.
    5. Dedicated third-model release auditor — production should use a
       separately configured auditor model for criticality bias detection.
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
    "ADVISORY ONLY — This AI-generated batch-release deviation disposition is "
    "decision-support, not a batch-release decision. A qualified Qualified "
    "Person / Quality Release approver must independently confirm the deviation "
    "criticality, CQA impact, and disposition before any batch is released or "
    "rejected. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found a "
    "'release' disposition proposed for a batch with an unresolved critical "
    "deviation affecting a CQA or patient safety. See metadata['veto_reason']. "
    "Escalate to the Qualified Person; the batch must not be released until the "
    "deviation is resolved."
)

_FLAG_HEADERS = ("CRITICALITY FLAGS:", "IMPACT-ASSESSMENT FLAGS:", "RELEASE-RISK FLAGS:")

_BATCH_RELEASE_REVIEW_CRITERIA = """\
Evaluate this batch-release deviation disposition on five dimensions. Score each 0–10.

1. DEVIATION CRITICALITY (30%) — CRITICAL
   Is the deviation criticality (minor / major / critical) correct for its impact
   on the CQA and patient safety? Penalise a deviation under-classified relative
   to its CQA/safety impact. Flag under CRITICALITY FLAGS:.

2. IMPACT ASSESSMENT (25%) — CRITICAL
   Is the impact on product quality and safety fully assessed, with every
   affected CQA identified? Penalise an incomplete impact assessment or a missed
   affected CQA. Flag under IMPACT-ASSESSMENT FLAGS:.

3. RELEASE-RISK JUDGMENT (20%) — CRITICAL
   Does the proposed disposition leave unresolved risk to the patient or the CQA?
   Penalise a release with unresolved risk. Flag under RELEASE-RISK FLAGS:.

4. CAPA-LINKAGE / ROOT-CAUSE (15%)
   Is the root cause established and linked to an adequate CAPA? Penalise a
   disposition without a sound root cause or CAPA linkage.

5. ACTIONABILITY (10%)
   Is the disposition specific enough to act on (criticality, CQA, CAPA, release
   decision)? Penalise vague dispositions.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a 'release' disposition is proposed for a batch with an
unresolved critical deviation affecting a CQA or patient safety.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero CRITICALITY FLAGS AND zero IMPACT-ASSESSMENT FLAGS AND
zero RELEASE-RISK FLAGS AND no VETO: ready for Qualified Person sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  CRITICALITY FLAGS: [bullet list, or "None detected"]
  IMPACT-ASSESSMENT FLAGS: [bullet list, or "None detected"]
  RELEASE-RISK FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are producing a batch-release deviation disposition for a qualified
Qualified Person / Quality Release approver. You have no stake in the outcome.
Your job is to classify the deviation criticality, assess CQA/safety impact,
judge the release risk, and recommend a disposition — grounded only in the data
supplied.

BASE THE DISPOSITION ON THE INPUT DATA ONLY.

BATCH-DEVIATION DATA:
{request_text}

{wiki_context}

Produce a structured disposition with exactly these sections:

## Deviation summary
Summarise the deviation, the batch, and the manufacturing step from the input.

## Criticality classification
Classify the deviation (minor / major / critical) against its CQA and patient-
safety impact. Do not under-classify a deviation that affects a CQA.

## Impact assessment
Identify every affected critical quality attribute and the impact on product
quality and safety.

## Release-risk judgment
State whether the proposed disposition leaves unresolved risk to the patient or
the CQA.

## Root cause, CAPA, and disposition
State the root cause, the linked CAPA, and the recommended disposition (release /
reject / rework).

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this batch-release deviation disposition. Address EVERY issue in the
reviewer's critique, especially any CRITICALITY FLAGS, IMPACT-ASSESSMENT FLAGS,
or RELEASE-RISK FLAGS.

PREVIOUS DISPOSITION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any CRITICALITY flag: re-classify the deviation against its CQA/safety impact.
⚠️  For any IMPACT-ASSESSMENT flag: identify every affected CQA.
⚠️  For any RELEASE-RISK flag: state and resolve the unresolved risk before release.
"""


@dataclass
class BatchReleaseRequest:
    """Structured input for the batch-release deviation disposition workflow."""

    batch_identifier: str
    """Generic product category and lot/batch identifier."""

    deviation_description: str
    """What the deviation was and at which manufacturing step."""

    deviation_classification: str
    """Caller's proposed criticality (minor / major / critical)."""

    affected_cqas: str
    """Critical quality attributes potentially impacted."""

    impact_assessment_summary: str
    """Caller's assessment of quality / safety impact."""

    root_cause_summary: str
    """Root-cause finding for the deviation."""

    capa_status: str
    """Linked CAPA and its state."""

    proposed_disposition: str
    """Caller's proposed disposition (release / reject / rework)."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Batch identifier: {self.batch_identifier[:cap]}",
            f"Deviation description: {self.deviation_description[:cap]}",
            f"Deviation classification: {self.deviation_classification[:cap]}",
            f"Affected CQAs: {self.affected_cqas[:cap]}",
            f"Impact assessment summary: {self.impact_assessment_summary[:cap]}",
            f"Root cause summary: {self.root_cause_summary[:cap]}",
            f"CAPA status: {self.capa_status[:cap]}",
            f"Proposed disposition: {self.proposed_disposition[:cap]}",
        ])


class BatchReleaseDeviationWorkflow(BaseWorkflow):
    """
    Adversarial batch-release deviation disposition: executor dispositions a
    batch carrying a deviation → reviewer challenges under-classified
    criticality, incomplete impact assessment, and unresolved release risk, with
    the power to VETO → iterate.

    Convergence gate (D-LIFESCI-4):
        score ≥ threshold (8.0)
        AND zero CRITICALITY FLAGS
        AND zero IMPACT-ASSESSMENT FLAGS
        AND zero RELEASE-RISK FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: BatchReleaseRequest,
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
                criteria=_BATCH_RELEASE_REVIEW_CRITERIA,
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

            if review.approved and not self._flag_classes_unresolved(
                review.critique, _FLAG_HEADERS, current.values()
            ):
                converged = True
                break

        batch_release_checklist = self._build_batch_release_checklist(
            request, accumulated, veto_reason
        )

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "batch_identifier": sanitize_for_prompt(
                request.batch_identifier, max_chars=200
            ),
            "criticality_flags": list(dict.fromkeys(accumulated["CRITICALITY FLAGS:"])),
            "impact_assessment_flags": list(
                dict.fromkeys(accumulated["IMPACT-ASSESSMENT FLAGS:"])
            ),
            "release_risk_flags": list(
                dict.fromkeys(accumulated["RELEASE-RISK FLAGS:"])
            ),
            "batch_release_checklist": batch_release_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the Qualified Person sees what the AI produced before the REVIEWER
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
            "CRITICALITY FLAGS:": (
                "⚠️  CRITICALITY FLAGS (re-classify the deviation against its "
                "CQA/safety impact):"
            ),
            "IMPACT-ASSESSMENT FLAGS:": (
                "⚠️  IMPACT-ASSESSMENT FLAGS (identify every affected CQA):"
            ),
            "RELEASE-RISK FLAGS:": (
                "⚠️  RELEASE-RISK FLAGS (state and resolve the unresolved risk "
                "before release):"
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
    def _build_batch_release_checklist(
        request: BatchReleaseRequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Qualified Person / Quality Release]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — a 'release' disposition is proposed for a "
                "batch with an unresolved critical deviation; escalate to the QP "
                "and do not release until the deviation is resolved"
            )
        criticality_flags = accumulated.get("CRITICALITY FLAGS:", [])
        impact_assessment_flags = accumulated.get("IMPACT-ASSESSMENT FLAGS:", [])
        release_risk_flags = accumulated.get("RELEASE-RISK FLAGS:", [])
        if criticality_flags:
            checklist.append(
                f"[ ] ⚠️  CRITICALITY FLAGS ({len(criticality_flags)}) — "
                "re-classify each deviation against its CQA/safety impact"
            )
        if impact_assessment_flags:
            checklist.append(
                f"[ ] ⚠️  IMPACT-ASSESSMENT FLAGS ({len(impact_assessment_flags)}) — "
                "identify every affected CQA"
            )
        if release_risk_flags:
            checklist.append(
                f"[ ] ⚠️  RELEASE-RISK FLAGS ({len(release_risk_flags)}) — resolve "
                "the unresolved risk before release"
            )
        checklist.extend([
            "[ ] Re-classify the deviation criticality against its CQA/safety impact",
            "[ ] Identify every affected CQA in the impact assessment",
            "[ ] Establish the root cause and link an adequate CAPA",
            "[ ] Confirm no batch is released except by the QP through the "
            "controlled release register",
            "[ ] Obtain Qualified Person sign-off before the disposition is executed",
        ])
        return checklist
