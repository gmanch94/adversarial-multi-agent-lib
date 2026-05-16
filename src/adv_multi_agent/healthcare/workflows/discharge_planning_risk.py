"""
Workflow — Discharge Planning Risk (Healthcare Domain)
Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for discharge planning risk
assessment. Executor proposes a discharge plan; reviewer (recommended: different
model family) challenges readmission risk, care gaps, and social-determinant
barriers.
If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.
⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. PHI de-identification — patient_summary and all fields are free-text;
       caller's responsibility to ensure HIPAA Safe Harbor / Expert
       Determination de-identification before submission.
    2. EHR integration — discharge plan data should be pulled from
       Epic/Cerner discharge module, not manually excerpted.
    3. Real-time bed availability — SNF/IRF/LTACH placement should query
       live bed-availability APIs, not rely on LLM knowledge.
    4. Payer authorization — post-acute service recommendations require
       prior auth verification against payer-specific rules.
    5. Readmission risk model — production should use a validated model
       (LACE, HOSPITAL score); LLM provides contextual adjustment,
       not baseline population risk.
    6. Dedicated SDOH auditor — production should add a third-model audit
       pass for social-determinant attention bias before discharge orders.
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
    "⚠️  ADVISORY ONLY — This AI-generated discharge plan is not an order "
    "set. A discharge planner / social worker must verify social-determinant "
    "context and confirm post-acute placement, follow-up appointments, and "
    "medication reconciliation before discharge. AI output must never replace "
    "clinical or care-coordination judgement."
)

_DISCHARGE_REVIEW_CRITERIA = """\
Evaluate this discharge plan on five dimensions. Score each 0–10.

1. READMISSION-RISK ASSESSMENT (30%)
   Is the readmission risk grounded in readmission_history and
   hospitalization_summary? Do not import baseline-population risk not
   present in the submitted data. LACE/HOSPITAL-equivalent rationale
   required for high-risk patients. Flag gaps under READMISSION FLAGS:.

2. CARE-GAP IDENTIFICATION (25%)
   Are specific missing services, referrals, or follow-up appointments
   named? Vague "ensure follow-up" is insufficient — name the service,
   provider type, and timeframe. Flag gaps under CARE-GAP FLAGS:.

3. SOCIAL-DETERMINANT ATTENTION (20%)
   Are transportation, housing, food security, and insurance barriers
   addressed with concrete actions (not aspirational language)?
   Flag unresolved barriers under SOCIAL-DETERMINANT FLAGS:.

4. PLAN ACTIONABILITY (15%)
   Does the plan specify destination, appointment dates/windows,
   and medication reconciliation? Penalise plans without specific
   post-acute placement or follow-up schedule.

5. CARE-TEAM ALIGNMENT (10%)
   Is the plan coherent with nursing, PT, OT, and SW notes?
   Contradictions with care_team_notes should reduce the score.

Overall score = weighted average.
Score ≥ 7.5 AND zero READMISSION FLAGS AND zero CARE-GAP FLAGS AND zero
SOCIAL-DETERMINANT FLAGS: ready for discharge planner review.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  READMISSION FLAGS: [bullet list, or "None detected"]
  CARE-GAP FLAGS: [bullet list, or "None detected"]
  SOCIAL-DETERMINANT FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are assessing discharge readiness and planning for a care coordinator to
review. You have no stake in the outcome. Base every recommendation on the
submitted patient data — not on general population norms.

BASE EVERY RECOMMENDATION ON THE INPUT DOCUMENTATION. Do not import
assumptions about social context or readmission risk not present in the
data below.

PATIENT DATA (caller-supplied — verify against EHR before acting):
{request_text}

{wiki_context}

Produce a discharge plan assessment with:

## Readmission risk
Anchor risk in readmission_history and hospitalization_summary.
State LACE/HOSPITAL-equivalent rationale if high-risk.

## Care gaps
Name each missing service, referral, or follow-up appointment with timeframe.

## Social-determinant context
Address transportation, housing, food security, and insurance barriers
with concrete actions.

## Discharge plan revisions
Specific changes to proposed_discharge_plan with owner and timeline.

## Claims
Specific factual claims about the patient data that ground the plan.
"""

_REVISION_PROMPT = """\
Revise the discharge plan assessment based on reviewer critique.

ORIGINAL ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: REMOVE the unsupported claim or replace it
with documentation evidence from the submitted patient data. Do not rephrase.
"""


@dataclass
class DischargePlanningRequest:
    """Structured input for the discharge planning risk workflow."""

    patient_summary: str
    """Brief patient demographics and active diagnoses."""

    hospitalization_summary: str
    """Current admission course, treatments, and clinical trajectory."""

    proposed_discharge_plan: str
    """Initial discharge plan including destination, follow-up, medications."""

    social_determinants: str
    """Transportation, housing, food security, insurance, support network."""

    readmission_history: str
    """Prior 30/90-day readmissions and validated risk scores (LACE, HOSPITAL)."""

    care_team_notes: str
    """Nursing, PT, OT, social work, and case management notes."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Patient summary: {self.patient_summary[:cap]}",
            f"Hospitalization summary: {self.hospitalization_summary[:cap]}",
            f"Proposed discharge plan: {self.proposed_discharge_plan[:cap]}",
            f"Social determinants: {self.social_determinants[:cap]}",
            f"Readmission history: {self.readmission_history[:cap]}",
            f"Care team notes: {self.care_team_notes[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "READMISSION FLAGS:",
    "CARE-GAP FLAGS:",
    "SOCIAL-DETERMINANT FLAGS:",
)


class DischargePlanningRiskWorkflow(BaseWorkflow):
    """
    Adversarial discharge planning risk assessment: executor proposes plan →
    reviewer challenges readmission risk, care gaps, and social determinants
    → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero READMISSION FLAGS
        AND zero CARE-GAP FLAGS
        AND zero SOCIAL-DETERMINANT FLAGS

    No reviewer veto — discharge plan revisions are reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: DischargePlanningRequest,
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
                criteria=_DISCHARGE_REVIEW_CRITERIA,
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

        discharge_checklist = self._build_discharge_checklist(request, accumulated)
        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "proposed_discharge_plan": request.proposed_discharge_plan[:200],
                "readmission_flags": list(dict.fromkeys(accumulated["READMISSION FLAGS:"])),
                "care_gap_flags": list(dict.fromkeys(accumulated["CARE-GAP FLAGS:"])),
                "social_determinant_flags": list(
                    dict.fromkeys(accumulated["SOCIAL-DETERMINANT FLAGS:"])
                ),
                "discharge_checklist": discharge_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "READMISSION FLAGS:": (
                "⚠️  READMISSION FLAGS (tighten or escalate post-acute follow-up; "
                "LACE/HOSPITAL-equivalent rationale required):"
            ),
            "CARE-GAP FLAGS:": (
                "⚠️  CARE-GAP FLAGS (name the missing service or referral; "
                "do not assume hand-off):"
            ),
            "SOCIAL-DETERMINANT FLAGS:": (
                "⚠️  SOCIAL-DETERMINANT FLAGS (address transportation, housing, "
                "food security, or insurance barriers; AI must not assume they "
                "resolve themselves):"
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
    def _build_discharge_checklist(
        request: DischargePlanningRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = []
        checklist.append(
            "[OWNER: Discharge Planner / Social Worker / Care Coordinator]"
        )
        if accumulated["READMISSION FLAGS:"]:
            checklist.append(
                "[ ] Escalate post-acute follow-up intensity for high readmission "
                "risk; document LACE/HOSPITAL-equivalent rationale in the plan"
            )
        if accumulated["CARE-GAP FLAGS:"]:
            checklist.append(
                "[ ] Confirm each named service, referral, and follow-up appointment "
                "is scheduled before discharge order is signed"
            )
        if accumulated["SOCIAL-DETERMINANT FLAGS:"]:
            checklist.append(
                "[ ] Verify transportation, housing, food security, and insurance "
                "barriers are concretely resolved — not assumed to self-resolve"
            )
        checklist.append(
            "[ ] Confirm medication reconciliation completed and patient/caregiver "
            "education documented"
        )
        checklist.append(
            "[ ] Confirm post-acute placement (SNF/IRF/home health/hospice) "
            "authorised by payer before discharge"
        )
        checklist.append(
            "[ ] Schedule 48-hour phone follow-up and 7-day in-person/telehealth "
            "appointment for high-risk patients"
        )
        checklist.append(
            "[ ] Document discharge summary in EHR and transmit to receiving "
            "provider / SNF / home health agency"
        )
        return checklist
