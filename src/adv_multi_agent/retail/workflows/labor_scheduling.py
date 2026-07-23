"""
Workflow — Labor Scheduling (Retail Teaching Example)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for retail labor
scheduling. Executor drafts a weekly store schedule; reviewer (recommended:
different model family per ARIS §2.1 principle 1) challenges coverage,
compliance with stated labor laws, cost efficiency, and fairness. Flags
labor law violations under COMPLIANCE FLAGS.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. HCM integration — staff_roster is free-text; production requires
       integration with HR / scheduling systems for real availability data.
    2. Automated labor law lookup — state_labor_law_notes is caller-supplied;
       production should pull rules from a jurisdiction database.
    3. Shift-swap and time-off handling — not modeled here.
    4. Payroll system write-back — schedule must not auto-publish.
    5. Manager approval gate — a store manager must review and publish
       the schedule; AI output must not go directly to employees.
    6. Dedicated third-model compliance auditor — this workflow folds the
       labor-law compliance check into the same reviewer that scores
       quality (single-stage), which differs from the ARIS three-stage
       assurance cascade. A production system should use a separately
       configured model (different family from BOTH executor and reviewer)
       whose only job is labor-law compliance verification. Legal
       interpretation of statutes by a single LLM is not a defensible
       compliance check. See ARIS §3.1.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import extract_flags, sanitize_for_prompt, truncate_flag_display
from ...core.workflow import BaseWorkflow, WorkflowResult

# L-PC-3: per-field cap — prevents a single oversized field crowding out
# later fields when the concatenated prompt is trimmed by sanitize_for_prompt.
_MAX_FIELD_CHARS = 1500

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated schedule is not a published roster. "
    "A store manager must review for compliance, fairness, and operational fit "
    "before publishing. AI output must never be shown directly to employees."
)

_SCHEDULE_REVIEW_CRITERIA = """\
Evaluate this labor schedule on five dimensions. Score each 0–10.

1. COVERAGE (30%)
   Are all peak hours (as stated in projected_traffic) covered with adequate
   staffing by role? Are there identifiable gaps where customer-facing roles
   are understaffed relative to projected volume?

2. COMPLIANCE (25%) — CRITICAL
   Check every shift against the stated labor law rules. Flag each violation
   under COMPLIANCE FLAGS:. Examples to check:
     • Overtime: hours exceeding the stated weekly OT threshold
     • Break requirements: shifts exceeding the stated minimum without a break noted
     • Availability: staff scheduled on days they stated as unavailable
     • Any other rule explicitly stated in the labor_law_notes
   If no violations: "COMPLIANCE FLAGS: None detected"

3. COST EFFICIENCY (20%)
   Is total estimated labor cost within the stated budget? Is overtime
   minimized where coverage allows? Is the schedule free of unnecessary overlap?

4. FAIRNESS (15%)
   Are hours distributed proportionately between FT and PT staff given their
   stated availability? Are no staff members disproportionately burdened with
   undesirable shifts without justification?

5. ACTIONABILITY (10%)
   Is the schedule specific enough to post: named assignments, day, start time,
   end time, role? Could a manager copy this directly to the break room board?

Overall score = weighted average.
Score ≥ 7.5: schedule is ready for manager review.
Score < 7.5: requires revision.

End your review with:
  Overall score: X/10
  Key issues: [bullet list]
  COMPLIANCE FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a weekly store schedule for a human store manager to review.
You have no stake in the outcome. Your job is coverage, compliance, and fairness.

BASE ALL SCHEDULING DECISIONS ON THE INPUT DATA. Do not assume staff availability,
wage rates, or labor rules not stated in the inputs.

STORE DATA:
{request_text}

{wiki_context}

Produce a structured schedule with exactly these sections:

## Schedule
Day-by-day assignments: for each day, list each staff member's name, role,
start time, end time. One line per assignment.

## Coverage Analysis
For each stated peak window, confirm which staff members cover it and whether
coverage is adequate relative to projected volume.

## Labor Cost Estimate
Estimate total hours per staff member. Estimate weekly cost using a reasonable
average wage (state your assumption explicitly). Compare to stated budget.

## Compliance Notes
State compliance status for each labor law rule listed in the inputs.
Note any potential violations proactively.

## Fairness Notes
Assess hour distribution across FT and PT staff. Note any availability
constraints honored or missed.

## Evidence Gaps
Information not in the inputs that would improve schedule quality.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this labor schedule. Address EVERY issue in the reviewer's critique,
especially any COMPLIANCE FLAGS.

PREVIOUS SCHEDULE:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any compliance flag: FIX the violation. Remove the offending shift
assignment and replace it with a compliant one. Do not note the violation
without fixing it.
"""


@dataclass
class SchedulingRequest:
    """Structured input for the labor scheduling workflow."""

    store_id: str
    """Store identifier, e.g. 'KRO-OH-0042'."""

    week_start: str
    """ISO date of week start (Monday)."""

    projected_traffic: str
    """Expected customer volume by day and peak hours."""

    staff_roster: str
    """Names, roles, FT/PT status, and availability constraints."""

    labor_budget: str
    """Weekly labor budget."""

    local_events: str
    """Events that affect foot traffic during this week."""

    state_labor_law_notes: str
    """Applicable labor rules: OT threshold, break requirements, minor labor rules."""

    unemployment_rate: str
    """Local unemployment rate and trend — staffing pool and wage pressure signal."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Store: {self.store_id[:cap]}",
            f"Week starting: {self.week_start[:cap]}",
            f"Projected traffic: {self.projected_traffic[:cap]}",
            f"Staff roster: {self.staff_roster[:cap]}",
            f"Labor budget: {self.labor_budget[:cap]}",
            f"Local events: {self.local_events[:cap]}",
            f"Labor law (stated): {self.state_labor_law_notes[:cap]}",
            f"Unemployment rate: {self.unemployment_rate[:cap]}",
        ])


class LaborSchedulingWorkflow(BaseWorkflow):
    """
    Adversarial labor scheduling: executor drafts schedule → reviewer
    challenges coverage and compliance → iterate.

    Convergence gate: score ≥ threshold AND zero COMPLIANCE FLAGS.
    """

    async def run(  # type: ignore[override]
        self,
        request: SchedulingRequest,
        **_: Any,
    ) -> WorkflowResult:
        """Run the adversarial scheduling loop."""
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_flags: list[str] = []
        all_flags: list[str] = []

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    request_text=request_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                flag_section = ""
                if current_flags:
                    flags_text = "\n".join(
                        f"  - {f}" for f in truncate_flag_display(current_flags)
                    )
                    flag_section = (
                        f"\n⚠️  COMPLIANCE FLAGS (must be fixed, not noted):\n"
                        f"{flags_text}\n"
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
                criteria=_SCHEDULE_REVIEW_CRITERIA,
            )
            score = review.score
            current_flags = extract_flags(review.critique, "COMPLIANCE FLAGS:")
            all_flags.extend(current_flags)

            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=config.max_wiki_body_chars),
                round_num=round_num,
                score=score,
            )

            if review.approved and not current_flags:
                converged = True
                break

        manager_checklist = self._build_manager_checklist(request, all_flags)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "store_id": sanitize_for_prompt(request.store_id, max_chars=200),
                "week_start": sanitize_for_prompt(request.week_start, max_chars=200),
                "compliance_flags": list(dict.fromkeys(all_flags)),
                "manager_checklist": manager_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _build_manager_checklist(
        request: SchedulingRequest,
        compliance_flags: list[str],
    ) -> list[str]:
        checklist: list[str] = []
        if compliance_flags:
            checklist.append(
                f"[ ] ⚠️  COMPLIANCE FLAGS DETECTED ({len(compliance_flags)}) — "
                "resolve ALL violations before publishing schedule"
            )
        checklist.extend([
            f"[ ] Verify staff availability for week of {request.week_start}",
            "[ ] Confirm all shifts comply with state labor law requirements",
            "[ ] Check total hours per employee against OT threshold",
            "[ ] Verify budget: total estimated cost vs. approved labor budget",
            "[ ] Review peak coverage for projected high-traffic periods",
            "[ ] Publish schedule — AI output must not go directly to employees",
        ])
        return checklist
