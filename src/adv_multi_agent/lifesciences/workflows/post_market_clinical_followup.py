"""
Workflow — Post-Market Clinical Follow-up (PMCF) Adequacy Review (Lifesciences · Devices)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for EU MDR post-market clinical
follow-up. Executor summarizes the PMCF plan against the claimed benefits and
residual risks; reviewer (recommended: different model family) challenges an
under-evidenced clinical claim, a residual risk with no PMCF activity, and a
PMCF method inadequate to answer its objective.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Clinical-evidence + literature-management system — the evidence baseline
       and literature should resolve against the controlled evidence system, not
       caller-pasted text.
    2. PMCF study / registry data platform — PMCF data should resolve against the
       controlled study/registry data source, not a manual summary.
    3. PMS / PSUR system — PMCF conclusions should feed the controlled
       post-market-surveillance and periodic-safety-update systems.
    4. Risk-management-file integration — residual risks should be read from the
       live risk-management file, not a caller-supplied reference.
    5. Qualified approver gate — every AI-suggested PMCF conclusion must be
       reviewed by qualified Clinical Affairs / Post-Market Surveillance. Output
       is never an auto-filed PMCF evaluation.
    6. Dedicated third-model PMCF auditor — production should use a separately
       configured auditor model for evidence-gap bias detection. See ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated PMCF adequacy review is decision-support, "
    "not a post-market clinical follow-up evaluation of record and not a "
    "regulatory submission. Qualified Clinical Affairs / Post-Market Surveillance "
    "must independently confirm the evidence sufficiency, residual-risk coverage, "
    "and method adequacy before any PMCF conclusion is filed. Not legal or "
    "medical advice."
)

_PMCF_REVIEW_CRITERIA = """\
Evaluate this PMCF adequacy review on five dimensions. Score each 0–10.

1. EVIDENCE SUFFICIENCY (30%) — CRITICAL
   Is every claimed clinical benefit and indication supported by sufficient
   post-market evidence? Penalise a claim with insufficient evidence. Flag under
   EVIDENCE-GAP FLAGS:.

2. RESIDUAL-RISK COVERAGE (25%) — CRITICAL
   Does every residual risk have a PMCF activity that confirms or monitors it?
   Penalise a residual risk with no covering activity. Flag under
   RESIDUAL-RISK FLAGS:.

3. PMCF-METHOD ADEQUACY (20%) — CRITICAL
   Is each PMCF method (study, registry, literature, real-world data) adequate to
   answer its stated objective and detect the risk? Penalise a method that cannot
   answer its objective. Flag under PMCF-ADEQUACY FLAGS:.

4. BENEFIT-RISK / PMS INTEGRATION (15%)
   Do the PMCF outputs feed the benefit-risk determination and the PSUR/PMS
   system? Penalise a PMCF that does not integrate with post-market surveillance.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which claim, which risk, which
   method)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero EVIDENCE-GAP FLAGS AND zero RESIDUAL-RISK FLAGS AND zero
PMCF-ADEQUACY FLAGS: ready for Clinical Affairs sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  EVIDENCE-GAP FLAGS: [bullet list, or "None detected"]
  RESIDUAL-RISK FLAGS: [bullet list, or "None detected"]
  PMCF-ADEQUACY FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are reviewing a post-market clinical follow-up (PMCF) plan for Clinical
Affairs to approve. You have no stake in the outcome. Assess the evidence
sufficiency for the claimed benefits, the coverage of residual risks, and the
adequacy of each PMCF method — grounded only in the data supplied, not general
device norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert a claim, risk, or method
that is not present below.

PMCF PLAN (caller-supplied — verify against the controlled evidence/PMS systems
before acting):
{request_text}

{wiki_context}

Produce a review with:

## Evidence sufficiency
- Each claimed benefit/indication and whether the post-market evidence supports it

## Residual-risk coverage
- Each residual risk and the PMCF activity covering it (or the gap)

## PMCF-method adequacy
- Each method and whether it can answer its objective / detect the risk

## Benefit-risk and PMS integration
- Whether PMCF outputs feed the benefit-risk update and the PSUR/PMS system

## Gaps and recommendations
- Specific, closeable gaps (which claim, which risk, which method)

## Claims
- Specific factual claims about the PMCF plan that ground the review
"""

_REVISION_PROMPT = """\
Revise the PMCF adequacy review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact under-evidenced claim, uncovered residual
risk, or inadequate method from the supplied plan; do not assert one not in the input.
"""


@dataclass
class PMCFRequest:
    """Structured input for the PMCF adequacy review workflow."""

    device_description: str
    """Generic device category and indication."""

    clinical_evidence_baseline: str
    """Clinical evidence available at market entry."""

    pmcf_objectives: str
    """The residual questions the PMCF is designed to answer."""

    pmcf_methods: str
    """PMCF methods: studies, registries, literature, real-world data."""

    residual_risks: str
    """Risks needing ongoing post-market confirmation."""

    benefit_risk_baseline: str
    """The current benefit-risk determination."""

    data_collected_summary: str
    """PMCF data gathered to date."""

    pms_linkage: str
    """How PMCF feeds the PMS / PSUR system."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Device description: {self.device_description[:cap]}",
            f"Clinical evidence baseline: {self.clinical_evidence_baseline[:cap]}",
            f"PMCF objectives: {self.pmcf_objectives[:cap]}",
            f"PMCF methods: {self.pmcf_methods[:cap]}",
            f"Residual risks: {self.residual_risks[:cap]}",
            f"Benefit-risk baseline: {self.benefit_risk_baseline[:cap]}",
            f"Data collected summary: {self.data_collected_summary[:cap]}",
            f"PMS linkage: {self.pms_linkage[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "EVIDENCE-GAP FLAGS:",
    "RESIDUAL-RISK FLAGS:",
    "PMCF-ADEQUACY FLAGS:",
)


class PostMarketClinicalFollowupWorkflow(BaseWorkflow):
    """
    Adversarial PMCF adequacy review: executor assesses evidence sufficiency,
    residual-risk coverage, and method adequacy → reviewer challenges an
    under-evidenced claim, an uncovered residual risk, and an inadequate PMCF
    method → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero EVIDENCE-GAP FLAGS
        AND zero RESIDUAL-RISK FLAGS
        AND zero PMCF-ADEQUACY FLAGS

    No reviewer veto — PMCF-plan corrections are reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: PMCFRequest,
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
                criteria=_PMCF_REVIEW_CRITERIA,
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

            if review.approved and not self._flag_classes_unresolved(
                review.critique, _FLAG_HEADERS, current.values()
            ):
                converged = True
                break

        pmcf_checklist = self._build_pmcf_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "device_description": sanitize_for_prompt(
                    request.device_description, max_chars=200
                ),
                "evidence_gap_flags": list(
                    dict.fromkeys(accumulated["EVIDENCE-GAP FLAGS:"])
                ),
                "residual_risk_flags": list(
                    dict.fromkeys(accumulated["RESIDUAL-RISK FLAGS:"])
                ),
                "pmcf_adequacy_flags": list(
                    dict.fromkeys(accumulated["PMCF-ADEQUACY FLAGS:"])
                ),
                "pmcf_checklist": pmcf_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "EVIDENCE-GAP FLAGS:": (
                "⚠️  EVIDENCE-GAP FLAGS (name the claimed benefit/indication with "
                "insufficient post-market evidence):"
            ),
            "RESIDUAL-RISK FLAGS:": (
                "⚠️  RESIDUAL-RISK FLAGS (name the residual risk with no covering "
                "PMCF activity):"
            ),
            "PMCF-ADEQUACY FLAGS:": (
                "⚠️  PMCF-ADEQUACY FLAGS (name the method that cannot answer its "
                "objective / detect the risk):"
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
    def _build_pmcf_checklist(
        request: PMCFRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: Clinical Affairs / Post-Market Surveillance]"]
        if accumulated["EVIDENCE-GAP FLAGS:"]:
            checklist.append(
                "[ ] Add post-market evidence for every flagged clinical claim, or "
                "narrow the claim"
            )
        if accumulated["RESIDUAL-RISK FLAGS:"]:
            checklist.append(
                "[ ] Add a PMCF activity covering every flagged residual risk"
            )
        if accumulated["PMCF-ADEQUACY FLAGS:"]:
            checklist.append(
                "[ ] Replace or strengthen every flagged method so it can answer "
                "its objective"
            )
        checklist.extend([
            "[ ] Confirm every claimed benefit maps to sufficient post-market evidence",
            "[ ] Confirm every residual risk has a covering PMCF activity",
            "[ ] Confirm PMCF outputs feed the benefit-risk update and the PSUR/PMS system",
            "[ ] Obtain Clinical Affairs sign-off before the PMCF evaluation is filed",
        ])
        return checklist
