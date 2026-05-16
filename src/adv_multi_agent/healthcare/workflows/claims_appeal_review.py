"""
Workflow — Claims Appeal Review (Healthcare Domain)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for claims appeal review.
Executor evaluates the appeal and original denial; reviewer (recommended:
different model family) challenges evidence grounding, coverage-policy
alignment, and procedural compliance.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.

PRODUCTION_GAPS:
    1. PHI de-identification — claim_id and all fields are free-text;
       caller's responsibility to de-identify before submission.
    2. Claims system integration — production must pull from TriZetto,
       Facets, or equivalent adjudication platform; no manual copy-paste.
    3. Coverage policy version control — policy text must be effective-date-
       versioned; wrong version creates liability.
    4. Medical director sign-off gate — first-level clinical appeals require
       physician review before any overturn or uphold decision is issued.
    5. ERISA / state appeal timeline tracking — 72h urgent / 30-day standard
       ERISA deadlines must be enforced by the claims system, not by AI output.
    6. Dedicated third-model causality auditor — production should add a
       third-model audit pass to verify causality chains before issuing
       any overturn determination.
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
    "ADVISORY ONLY — This AI-generated appeal review is not an overturn or "
    "uphold determination. A medical director (for first-level clinical appeals) "
    "or external review organization (for second-level) must independently render "
    "the decision."
)

_CLAIMS_APPEAL_REVIEW_CRITERIA = """\
Evaluate this claims appeal review on five dimensions. Score each 0–10.

1. EVIDENCE STRENGTH (30%)
   Does the clinical evidence directly support or contradict the original denial?
   Are labs, imaging, and treatment failure documented with specifics?
   Flag unsupported or vague evidence claims under EVIDENCE FLAGS:.

2. COVERAGE-POLICY ALIGNMENT (25%)
   Is the effective-date-versioned coverage policy cited correctly?
   Interpretation must be plain-language only — no extrapolation beyond what
   the policy text states. Flag gaps or overreach under COVERAGE FLAGS:.

3. PROCEDURAL COMPLIANCE (20%)
   Was the appeal received within the required timeline (72h urgent /
   30 days standard ERISA)? Were required notifications sent?
   Flag timeline or notification gaps under PROCEDURE FLAGS:.

4. CONSISTENCY WITH ORIGINAL DENIAL (15%)
   Were the original review criteria (e.g., InterQual, MCG) applied correctly?
   Does the appeal identify a specific error in the original determination?
   Flag inconsistencies under EVIDENCE FLAGS:.

5. DECISION CLARITY (10%)
   Is the recommendation (overturn / uphold / route to external review)
   specific and actionable?
   Vague recommendations reduce the score.

Overall score = weighted average.
Score >= 7.5 AND zero EVIDENCE FLAGS AND zero COVERAGE FLAGS AND zero \
PROCEDURE FLAGS required for convergence.
"""

_INITIAL_PROMPT = """\
You are a healthcare claims appeal specialist. Review the following appeal
submission and produce a structured appeal review.

APPEAL SUBMISSION:
{request_text}

{wiki_context}

Produce a structured review with these sections:

## Evidence assessment
Evaluate the clinical evidence (labs, imaging, treatment failure) that supports
or contradicts the original denial. Cite specific findings.

## Coverage-policy alignment
Cite the effective-date-versioned coverage policy section. Interpret plain
language only — do not extrapolate beyond policy text.

## Procedural review
Confirm appeal timeline compliance (72h urgent / 30 days standard ERISA)
and required notifications.

## Consistency with original denial
Assess whether the original review criteria were applied correctly and identify
any specific error in the original determination.

## Recommendation
State overturn / uphold / route to external review with rationale.

## Claims
Specific factual claims from the submitted data that ground the recommendation.
"""

_REVISION_PROMPT = """\
Revise the claims appeal review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.

⚠️  For any flagged item: REMOVE the unsupported claim or replace it with
evidence from the submitted appeal data and cited coverage policy.
Do not rephrase — ground or remove.
"""


@dataclass
class ClaimsAppealRequest:
    """Structured input for the claims appeal review workflow."""

    claim_id: str
    """Claims adjudication identifier (de-identify before submission)."""

    denied_service: str
    """Procedure, drug, or device denied with CPT/HCPCS/NDC code."""

    appeal_narrative: str
    """Member or provider narrative explaining grounds for appeal."""

    clinical_evidence: str
    """Supporting clinical evidence: labs, imaging, treatment failure, guidelines."""

    coverage_policy: str
    """Effective-date-versioned coverage policy text relevant to the denied service."""

    original_review_summary: str
    """Summary of the original denial rationale and criteria applied."""

    treating_physician_statement: str
    """Treating physician attestation supporting medical necessity of the denied service."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Claim ID: {self.claim_id[:cap]}",
            f"Denied service: {self.denied_service[:cap]}",
            f"Appeal narrative: {self.appeal_narrative[:cap]}",
            f"Clinical evidence: {self.clinical_evidence[:cap]}",
            f"Coverage policy: {self.coverage_policy[:cap]}",
            f"Original review summary: {self.original_review_summary[:cap]}",
            f"Treating physician statement: {self.treating_physician_statement[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "EVIDENCE FLAGS:",
    "COVERAGE FLAGS:",
    "PROCEDURE FLAGS:",
)


class ClaimsAppealReviewWorkflow(BaseWorkflow):
    """
    Adversarial claims appeal review: executor evaluates the appeal and original
    denial → reviewer challenges evidence grounding, coverage-policy alignment,
    and procedural compliance → iterate.

    Convergence gate:
        score >= threshold
        AND zero EVIDENCE FLAGS
        AND zero COVERAGE FLAGS
        AND zero PROCEDURE FLAGS

    No reviewer veto — appeal revisions are reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: ClaimsAppealRequest,
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
                criteria=_CLAIMS_APPEAL_REVIEW_CRITERIA,
            )
            score = review.score

            for header in _FLAG_HEADERS:
                current[header] = extract_flags(review.critique, header)
                accumulated[header].extend(current[header])

            self.wiki.add_feedback(
                sanitize_for_prompt(
                    review.critique, max_chars=config.max_wiki_body_chars
                ),
                round_num=round_num,
                score=score,
            )

            if review.approved and not any(current.values()):
                converged = True
                break

        appeal_checklist = self._build_appeal_checklist(accumulated)
        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "denied_service": request.denied_service[:200],
                "evidence_flags": list(
                    dict.fromkeys(accumulated["EVIDENCE FLAGS:"])
                ),
                "coverage_flags": list(
                    dict.fromkeys(accumulated["COVERAGE FLAGS:"])
                ),
                "procedure_flags": list(
                    dict.fromkeys(accumulated["PROCEDURE FLAGS:"])
                ),
                "appeal_checklist": appeal_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "EVIDENCE FLAGS:": (
                "EVIDENCE FLAGS (address the specific clinical evidence — labs, "
                "imaging, treatment failure — that supports or contradicts the "
                "original denial):"
            ),
            "COVERAGE FLAGS:": (
                "COVERAGE FLAGS (cite the effective-date-versioned coverage policy; "
                "do not interpret beyond plain language):"
            ),
            "PROCEDURE FLAGS:": (
                "PROCEDURE FLAGS (verify appeal timeline (72h urgent, 30 days "
                "standard ERISA) and required notifications):"
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
    def _build_appeal_checklist(
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append("[OWNER: Appeals Coordinator / Medical Director]")
        checklist.append(
            "[ ] Confirm appeal received within plan timeline "
            "(72h urgent / 30 days standard ERISA)"
        )
        checklist.append(
            "[ ] Verify coverage policy version effective at date of service"
        )
        checklist.append(
            "[ ] Route first-level clinical appeals to medical director; "
            "second-level to external review organization"
        )
        checklist.append(
            "[ ] Notify member of decision with appeal rights and timeline"
        )
        checklist.append(
            "[ ] Document rationale citing specific coverage policy section "
            "+ clinical evidence"
        )
        for flag in dict.fromkeys(accumulated.get("EVIDENCE FLAGS:", [])):
            checklist.append(
                f"[ ] Resolve evidence gap: {sanitize_for_prompt(flag, max_chars=200)}"
            )
        for flag in dict.fromkeys(accumulated.get("COVERAGE FLAGS:", [])):
            checklist.append(
                f"[ ] Resolve coverage gap: {sanitize_for_prompt(flag, max_chars=200)}"
            )
        for flag in dict.fromkeys(accumulated.get("PROCEDURE FLAGS:", [])):
            checklist.append(
                f"[ ] Resolve procedural gap: {sanitize_for_prompt(flag, max_chars=200)}"
            )
        return checklist
