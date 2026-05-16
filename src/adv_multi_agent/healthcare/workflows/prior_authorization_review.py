"""
Workflow — Prior Authorization Review (Healthcare Domain)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for prior authorization
review. Executor assesses medical necessity and coverage fit; reviewer
(recommended: different model family) challenges necessity grounding,
coverage-policy alignment, and documentation sufficiency.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.

PRODUCTION_GAPS:
    1. PHI de-identification — member_id and all fields are free-text;
       caller's responsibility to ensure HIPAA Safe Harbor / Expert
       Determination de-identification before submission.
    2. Real-time eligibility — member benefit and eligibility at the date
       of service must be verified against the payer's claims system, not
       inferred from submitted data.
    3. InterQual / MCG integration — clinical necessity criteria should be
       pulled from a licensed InterQual / MCG API; LLM knowledge of
       guideline versions may be stale.
    4. PA system integration — production should integrate with PA
       automation platforms (Cohere Health, AIM Specialty Health, etc.)
       for rule-based pre-screening before LLM review.
    5. Peer-to-peer review gate — denial recommendations require physician
       (medical director) review before issuance; AI output must never
       auto-deny.
    6. Dedicated third-model bias auditor — production should add a
       third-model audit pass for parity / protected-class detection before
       any adverse determination is issued.
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
    "ADVISORY ONLY — This AI-generated prior auth review is not a coverage "
    "determination. A licensed nurse reviewer or medical director must verify "
    "medical necessity against the payer's coverage policy before issuing any "
    "approval or denial. AI output must never auto-approve or auto-deny."
)

_PRIOR_AUTH_REVIEW_CRITERIA = """\
Evaluate this prior authorization request on five dimensions. Score each 0–10.

1. MEDICAL-NECESSITY GROUNDING (30%)
   Is every necessity claim grounded in the submitted clinical_guidelines
   (e.g., InterQual, MCG, ACC/AHA)? Do not paraphrase from general clinical
   practice or LLM training knowledge not present in the submitted data.
   Flag unsupported necessity claims under MEDICAL-NECESSITY FLAGS:.

2. COVERAGE-POLICY FIT (25%)
   Does the requested service match a specific coverage policy section cited
   in clinical_guidelines? If the service is outside stated policy or
   coverage is ambiguous, recommend medical-director review rather than
   approval. Flag gaps under COVERAGE FLAGS:.

3. DOCUMENTATION SUFFICIENCY (20%)
   Are all required documentation elements present (diagnostic confirmation,
   NYHA/functional class, step-therapy evidence, prescriber attestation)?
   Name any missing element specifically — do not approve without it.
   Flag gaps under DOCUMENTATION FLAGS:.

4. STEP-THERAPY VERIFICATION (15%)
   Are the alternatives_tried consistent with the payer's step therapy
   requirements for this service? Verify that each required step is
   documented with duration and outcome. Flag gaps under COVERAGE FLAGS:.

5. DECISION CLARITY (10%)
   Is the recommendation (approve / pend for additional information /
   deny / route to medical director) specific and actionable?
   Vague recommendations reduce the score.

Overall score = weighted average.
Score ≥ 7.5 AND zero MEDICAL-NECESSITY FLAGS AND zero COVERAGE FLAGS AND
zero DOCUMENTATION FLAGS: ready for nurse reviewer sign-off.
Otherwise: requires revision or escalation.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  MEDICAL-NECESSITY FLAGS: [bullet list, or "None detected"]
  COVERAGE FLAGS: [bullet list, or "None detected"]
  DOCUMENTATION FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are conducting a prior authorization review for a licensed nurse reviewer
to verify. You have no stake in the outcome. Base every assessment on the
submitted member data and cited clinical guidelines — not on general practice
or assumptions not present in the data below.

BASE EVERY NECESSITY CLAIM ON THE SUBMITTED CLINICAL GUIDELINES. Do not
paraphrase from general clinical knowledge not present in the data below.

MEMBER DATA (caller-supplied — verify against payer system before acting):
{request_text}

{wiki_context}

Produce a prior authorization review with:

## Medical-necessity assessment
Ground every necessity claim in a specific section of clinical_guidelines.

## Coverage-policy fit
Cite the specific coverage policy section; flag if outside policy.

## Documentation review
Name any missing documentation element specifically.

## Step-therapy verification
Verify each step in alternatives_tried against payer step-therapy requirements.

## Recommendation
Specific and actionable: approve / pend for additional info / deny / route to
medical director. State the basis.

## Claims
Specific factual claims from the submitted data that ground the recommendation.
"""

_REVISION_PROMPT = """\
Revise the prior authorization review based on reviewer critique.

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
documentation evidence from the submitted member data and cited guidelines.
Do not rephrase — ground or remove.
"""


@dataclass
class PriorAuthRequest:
    """Structured input for the prior authorization review workflow."""

    member_id: str
    """Plan member identifier (de-identify before submission)."""

    requested_service: str
    """Drug, device, or procedure being requested with strength/quantity."""

    clinical_rationale: str
    """Prescriber's medical-necessity rationale with diagnostic evidence."""

    diagnosis_codes: str
    """ICD-10 diagnosis codes supporting the request."""

    clinical_guidelines: str
    """Cited clinical guidelines or coverage criteria (InterQual, MCG, specialty society)."""

    member_history: str
    """Relevant prior claims, active medications, and comorbidities."""

    alternatives_tried: str
    """Step-therapy history: alternatives tried with duration and outcome."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Member ID: {self.member_id[:cap]}",
            f"Requested service: {self.requested_service[:cap]}",
            f"Clinical rationale: {self.clinical_rationale[:cap]}",
            f"Diagnosis codes: {self.diagnosis_codes[:cap]}",
            f"Clinical guidelines: {self.clinical_guidelines[:cap]}",
            f"Member history: {self.member_history[:cap]}",
            f"Alternatives tried: {self.alternatives_tried[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "MEDICAL-NECESSITY FLAGS:",
    "COVERAGE FLAGS:",
    "DOCUMENTATION FLAGS:",
)


class PriorAuthorizationReviewWorkflow(BaseWorkflow):
    """
    Adversarial prior authorization review: executor assesses necessity and
    coverage fit → reviewer challenges necessity grounding, coverage-policy
    alignment, and documentation sufficiency → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero MEDICAL-NECESSITY FLAGS
        AND zero COVERAGE FLAGS
        AND zero DOCUMENTATION FLAGS

    No reviewer veto — prior auth revisions are reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: PriorAuthRequest,
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
                criteria=_PRIOR_AUTH_REVIEW_CRITERIA,
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

        prior_auth_checklist = self._build_prior_auth_checklist(accumulated)
        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "requested_service": sanitize_for_prompt(
                    request.requested_service, max_chars=200
                ),
                "medical_necessity_flags": list(
                    dict.fromkeys(accumulated["MEDICAL-NECESSITY FLAGS:"])
                ),
                "coverage_flags": list(
                    dict.fromkeys(accumulated["COVERAGE FLAGS:"])
                ),
                "documentation_flags": list(
                    dict.fromkeys(accumulated["DOCUMENTATION FLAGS:"])
                ),
                "prior_auth_checklist": prior_auth_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "MEDICAL-NECESSITY FLAGS:": (
                "MEDICAL-NECESSITY FLAGS (ground every medical-necessity claim "
                "in the clinical guideline; do not paraphrase from general practice):"
            ),
            "COVERAGE FLAGS:": (
                "COVERAGE FLAGS (cite the specific coverage policy section; if "
                "outside policy, recommend medical-director review or peer-to-peer):"
            ),
            "DOCUMENTATION FLAGS:": (
                "DOCUMENTATION FLAGS (name the missing documentation specifically; "
                "request rather than approve without):"
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
    def _build_prior_auth_checklist(
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append(
            "[OWNER: Prior Authorization Nurse / Case Manager]"
        )
        checklist.append(
            "[ ] Confirm member eligibility and benefit at the date of service "
            "requested"
        )
        checklist.append(
            "[ ] Verify cited clinical guideline (InterQual / MCG) effective version"
        )
        checklist.append(
            "[ ] Document medical-necessity rationale citing specific guideline "
            "criteria"
        )
        checklist.append(
            "[ ] Route denials to medical director for physician review before "
            "issuance"
        )
        checklist.append(
            "[ ] Notify provider of decision within plan turnaround time "
            "(urgent 72h / standard 5 business days)"
        )
        return checklist
