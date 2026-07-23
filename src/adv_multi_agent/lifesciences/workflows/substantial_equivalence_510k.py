"""
Workflow — Substantial-Equivalence 510(k) Rationale Review (Lifesciences ·
Devices, Veto)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) applied to premarket
notification 510(k) substantial-equivalence rationale review: executor maps the
subject device to a candidate predicate across intended use, indications, and
technological characteristics; reviewer (cross-model per ARIS §2.1) challenges a
predicate with a different intended use, indications broader than the predicate's
cleared scope, and technological differences that raise new questions of safety
or effectiveness, with the power to VETO when the substantial-equivalence claim
is fundamentally unsupportable (near-certain Not-Substantially-Equivalent).

Veto gate (D-LIFESCI-2): fires when the substantial-equivalence claim is
fundamentally unsupportable — no valid predicate, or a technological difference
that plainly raises a new question of safety/effectiveness — such that asserting
SE would misrepresent equivalence to FDA.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. FDA 510(k) clearance database — candidate predicates should resolve
       against the controlled FDA 510(k) clearance database, not caller-pasted
       device names.
    2. Product-classification database (21 CFR 862–892) — device type, product
       code, and regulation number should reconcile against the controlled FDA
       product-classification database, not caller-supplied text.
    3. eSTAR builder — the released rationale must map into the controlled eSTAR
       submission template before any 510(k) is filed.
    4. Prior-submission archive — every predicate and prior interaction should
       reconcile against the controlled prior-submission archive.
    5. Dedicated third-model equivalence auditor — production should use a
       separately configured auditor model for equivalence-inflation bias
       detection. See ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated substantial-equivalence rationale is "
    "decision-support, not a 510(k) submission and not an FDA clearance. A "
    "qualified Regulatory Affairs lead must independently confirm predicate "
    "validity, indications scope, and technological equivalence before any "
    "submission. Not legal or medical advice."
)

_VETO_BANNER = (
    "REVIEWER VETO — workflow halted before convergence. The reviewer found the "
    "substantial-equivalence claim fundamentally unsupportable (near-certain "
    "Not-Substantially-Equivalent); asserting it would misrepresent equivalence "
    "to FDA. See metadata['veto_reason']. Escalate to Regulatory Affairs; "
    "consider De Novo / PMA."
)

_FLAG_HEADERS = ("PREDICATE-MISMATCH FLAGS:", "INDICATION-CREEP FLAGS:", "TECHNOLOGY-DELTA FLAGS:")

_SE_REVIEW_CRITERIA = """\
Evaluate this substantial-equivalence rationale on five dimensions. Score each 0–10.

1. PREDICATE VALIDITY (30%) — CRITICAL
   Does the candidate predicate share the same intended use and device type,
   making it a valid SE anchor? Penalise a predicate with a different intended
   use or device type. Flag under PREDICATE-MISMATCH FLAGS:.

2. INDICATIONS SCOPE (25%) — CRITICAL
   Are the subject device's indications-for-use within the predicate's cleared
   indications? Penalise indications broader than the predicate's. Flag under
   INDICATION-CREEP FLAGS:.

3. TECHNOLOGICAL DIFFERENCES (20%) — CRITICAL
   Do new technological characteristics raise new questions of safety or
   effectiveness (the Not-Substantially-Equivalent trigger)? Penalise a
   difference that raises a new question but is argued away. Flag under
   TECHNOLOGY-DELTA FLAGS:.

4. PERFORMANCE-DATA SUFFICIENCY (15%)
   Do the performance data actually address each identified difference?
   Penalise differences with no supporting data.

5. ACTIONABILITY (10%)
   Is each finding specific enough for RA to resolve (which predicate, which
   indication, which characteristic)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the substantial-equivalence claim is fundamentally unsupportable
(near-certain NSE — no valid predicate, or a technological difference that
plainly raises a new question of safety/effectiveness) such that asserting SE
would misrepresent equivalence to FDA.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero PREDICATE-MISMATCH FLAGS AND zero INDICATION-CREEP FLAGS
AND zero TECHNOLOGY-DELTA FLAGS AND no VETO: ready for Regulatory Affairs
sign-off. Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PREDICATE-MISMATCH FLAGS: [bullet list, or "None detected"]
  INDICATION-CREEP FLAGS: [bullet list, or "None detected"]
  TECHNOLOGY-DELTA FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
"""

_INITIAL_PROMPT = """\
You are preparing a substantial-equivalence rationale for a premarket
notification (510(k)) for a qualified Regulatory Affairs lead. You have no stake
in the outcome. Your job is to map the subject device to a candidate predicate
across intended use, indications, and technological characteristics, and to
assess whether substantial equivalence is defensible, grounded only in the data
supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

SUBSTANTIAL-EQUIVALENCE DATA:
{request_text}

{wiki_context}

Produce a structured substantial-equivalence rationale with exactly these sections:

## Predicate comparison
Map the subject device to each candidate predicate. State whether each predicate
shares the subject's intended use and device type, and identify the best anchor.

## Intended use and indications
Compare the subject device's indications-for-use against the predicate's cleared
indications. Identify any indication broader than the predicate's cleared scope.

## Technological characteristics
Compare the subject's technological characteristics to the predicate's. Identify
each difference and state whether it raises a new question of safety or
effectiveness.

## Performance-data bridge
For each identified technological difference, state whether the performance data
address the new question. Identify any difference with no supporting data.

## Substantial-equivalence conclusion
State whether the subject device is substantially equivalent to the cited
predicate, or whether it is Not-Substantially-Equivalent.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this substantial-equivalence rationale. Address EVERY issue in the
reviewer's critique, especially any PREDICATE-MISMATCH FLAGS, INDICATION-CREEP
FLAGS, or TECHNOLOGY-DELTA FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any PREDICATE-MISMATCH flag: select a predicate with matching intended
use, or acknowledge NSE.
⚠️  For any INDICATION-CREEP flag: narrow the subject indications to the
predicate's cleared scope.
⚠️  For any TECHNOLOGY-DELTA flag: cite performance data that resolves the new
question, or acknowledge it is unresolved.
"""


@dataclass
class SERequest:
    """Structured input for the substantial-equivalence 510(k) review workflow."""

    subject_device_description: str
    """Generic category and format of the subject device (e.g. a blood-glucose meter)."""

    intended_use: str
    """Intended-use statement: what the device measures / does and clinical purpose."""

    indications_for_use: str
    """Indications-for-use: target population, setting (OTC / professional), disease."""

    technological_characteristics: str
    """Technological characteristics: principle of operation, materials, energy source."""

    candidate_predicates: str
    """Candidate predicate device(s) cited as the substantial-equivalence anchor."""

    performance_data_summary: str
    """Performance / bench / clinical data supporting the subject device."""

    differences_from_predicate: str
    """Stated differences between the subject device and the predicate(s)."""

    prior_fda_interactions: str
    """Prior submissions, Q-Subs, or other FDA interactions for this device."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Subject device description: {self.subject_device_description[:cap]}",
            f"Intended use: {self.intended_use[:cap]}",
            f"Indications for use: {self.indications_for_use[:cap]}",
            f"Technological characteristics: {self.technological_characteristics[:cap]}",
            f"Candidate predicates: {self.candidate_predicates[:cap]}",
            f"Performance-data summary: {self.performance_data_summary[:cap]}",
            f"Differences from predicate: {self.differences_from_predicate[:cap]}",
            f"Prior FDA interactions: {self.prior_fda_interactions[:cap]}",
        ])


class SubstantialEquivalence510kWorkflow(BaseWorkflow):
    """
    Adversarial substantial-equivalence 510(k) rationale review: executor maps
    the subject device to a candidate predicate → reviewer challenges a predicate
    with a different intended use, indications broader than the predicate's
    cleared scope, and technological differences that raise new questions, with
    the power to VETO → iterate.

    Convergence gate (D-LIFESCI-2):
        score ≥ threshold (8.0)
        AND zero PREDICATE-MISMATCH FLAGS
        AND zero INDICATION-CREEP FLAGS
        AND zero TECHNOLOGY-DELTA FLAGS
        AND no REVIEWER VETO

    On veto: workflow halts immediately after writing the audit trail to the
    wiki. The verbatim veto directive is recorded in metadata['veto_reason'].
    metadata['first_draft'] captures the clean executor draft from the vetoed
    round (L-IND-2).
    """

    async def run(  # type: ignore[override]
        self,
        request: SERequest,
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
                criteria=_SE_REVIEW_CRITERIA,
            )
            score = review.score
            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            # Audit-trail writes happen BEFORE the veto check — preserves the
            # round-N draft in wiki + ledger even if vetoed (D-LIFESCI-2).
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

        se_checklist = self._build_se_checklist(request, accumulated, veto_reason)

        output_with_banner = self._compose_output(output, veto_reason)

        metadata: dict[str, Any] = {
            "subject_device_description": sanitize_for_prompt(
                request.subject_device_description, max_chars=200
            ),
            "predicate_mismatch_flags": list(
                dict.fromkeys(accumulated["PREDICATE-MISMATCH FLAGS:"])
            ),
            "indication_creep_flags": list(
                dict.fromkeys(accumulated["INDICATION-CREEP FLAGS:"])
            ),
            "technology_delta_flags": list(
                dict.fromkeys(accumulated["TECHNOLOGY-DELTA FLAGS:"])
            ),
            "se_checklist": se_checklist,
            "disclaimer": _DISCLAIMER,
            "ledger_summary": self.ledger.summary(),
        }
        if veto_reason is not None:
            metadata["veto_reason"] = veto_reason
            metadata["vetoed"] = True
            # L-IND-2: surface the clean executor draft from the vetoed round so
            # the Regulatory Affairs lead sees what the AI produced before the
            # REVIEWER VETO banner was prepended.
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
            "PREDICATE-MISMATCH FLAGS:": (
                "⚠️  PREDICATE-MISMATCH FLAGS (select a predicate with matching "
                "intended use and device type, or acknowledge NSE):"
            ),
            "INDICATION-CREEP FLAGS:": (
                "⚠️  INDICATION-CREEP FLAGS (narrow the subject indications to the "
                "predicate's cleared scope):"
            ),
            "TECHNOLOGY-DELTA FLAGS:": (
                "⚠️  TECHNOLOGY-DELTA FLAGS (cite performance data that resolves the "
                "new question, or acknowledge it is unresolved):"
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
    def _build_se_checklist(
        request: SERequest,
        accumulated: dict[str, list[str]],
        veto_reason: str | None,
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Regulatory Affairs Lead]"]
        if veto_reason is not None:
            checklist.append(
                "[ ] 🛑 REVIEWER VETO — do not assert substantial equivalence; "
                "escalate to Regulatory Affairs and consider De Novo / PMA before "
                "any submission"
            )
        predicate_flags = accumulated.get("PREDICATE-MISMATCH FLAGS:", [])
        indication_flags = accumulated.get("INDICATION-CREEP FLAGS:", [])
        technology_flags = accumulated.get("TECHNOLOGY-DELTA FLAGS:", [])
        if predicate_flags:
            checklist.append(
                f"[ ] ⚠️  PREDICATE-MISMATCH FLAGS ({len(predicate_flags)}) — "
                "confirm the predicate shares the subject's intended use and device type"
            )
        if indication_flags:
            checklist.append(
                f"[ ] ⚠️  INDICATION-CREEP FLAGS ({len(indication_flags)}) — "
                "narrow the subject indications to the predicate's cleared scope"
            )
        if technology_flags:
            checklist.append(
                f"[ ] ⚠️  TECHNOLOGY-DELTA FLAGS ({len(technology_flags)}) — "
                "resolve each technological difference with performance data"
            )
        checklist.extend([
            "[ ] Confirm the predicate's intended use matches the subject device",
            "[ ] Narrow the subject indications to the predicate's cleared scope",
            "[ ] Resolve each technological difference with supporting performance data",
            "[ ] Obtain Regulatory Affairs sign-off before any 510(k) submission",
        ])
        return checklist
