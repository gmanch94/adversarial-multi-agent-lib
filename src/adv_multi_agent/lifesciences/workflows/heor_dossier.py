"""
Workflow — HEOR Value Dossier Review (Lifesciences · Cross)

Demonstrates the ARIS adversarial pattern (Yang, Li, Li — SJTU + Shanghai
Innovation Institute, arXiv:2605.03042, May 2026) for a health-economics and
outcomes-research (HEOR) value dossier. Executor structures the value argument
(comparators, endpoints, economic model); reviewer (recommended: different model
family) challenges an inappropriate comparator, a surrogate endpoint used where a
final endpoint is required, and an over-optimistic model extrapolation.

If you use this workflow, cite the ARIS paper — see CITATION.cff in the
repo root.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Evidence-synthesis / systematic-review platform — the clinical evidence
       should resolve against the controlled evidence-synthesis system, not
       caller-pasted text.
    2. Health-economic modeling software — the cost-effectiveness / budget-impact
       model should resolve against the controlled modeling environment.
    3. HTA-submission templates + payer value-dossier system — the dossier should
       resolve against the controlled submission repository.
    4. Real-world-evidence data sources — RWE inputs should resolve against the
       controlled data sources, not a manual summary.
    5. Qualified approver gate — every AI-suggested value claim must be reviewed
       by a qualified HEOR / Market Access lead. Output is never an auto-submitted
       value dossier.
    6. Dedicated third-model HEOR auditor — production should use a separately
       configured auditor model for comparator/endpoint bias detection.
       See ARIS §3.1.
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
    "ADVISORY ONLY — This AI-generated HEOR value-dossier review is "
    "decision-support, not a value dossier of record and not an HTA/payer "
    "submission. A qualified HEOR / Market Access lead must independently confirm "
    "the comparator choice, endpoint relevance, and model extrapolations before "
    "any dossier is submitted. Not legal or medical advice."
)

_HEOR_REVIEW_CRITERIA = """\
Evaluate this HEOR value dossier on five dimensions. Score each 0–10.

1. COMPARATOR APPROPRIATENESS (30%) — CRITICAL
   Is every comparator appropriate to the decision problem and the target market
   (current standard of care)? Penalise an inappropriate or missing comparator.
   Flag under COMPARATOR FLAGS:.

2. ENDPOINT RELEVANCE (25%) — CRITICAL
   Does the dossier rely on patient-relevant final endpoints where required, or
   justify any surrogate/intermediate endpoint? Penalise an unjustified surrogate
   used in place of a final endpoint. Flag under ENDPOINT-RELEVANCE FLAGS:.

3. EXTRAPOLATION VALIDITY (20%) — CRITICAL
   Are the model extrapolations and assumptions supported by the evidence and not
   over-optimistic? Penalise an unsupported or optimistic extrapolation. Flag
   under EXTRAPOLATION FLAGS:.

4. MODEL TRANSPARENCY / EVIDENCE FIT (15%)
   Are model assumptions sourced and the model structure justified against the
   evidence? Penalise opaque or poorly-fitted modeling.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which comparator, which endpoint,
   which assumption)? Penalise vague findings.

Overall score = weighted average.
Score >= 7.5 AND zero COMPARATOR FLAGS AND zero ENDPOINT-RELEVANCE FLAGS AND zero
EXTRAPOLATION FLAGS: ready for HEOR lead sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  COMPARATOR FLAGS: [bullet list, or "None detected"]
  ENDPOINT-RELEVANCE FLAGS: [bullet list, or "None detected"]
  EXTRAPOLATION FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are reviewing an HEOR value dossier for an HEOR / Market Access lead to
approve. You have no stake in the outcome. Assess the comparator choice, endpoint
relevance, and model extrapolations — grounded only in the data supplied, not
general market norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert a comparator, endpoint,
or assumption that is not present below.

VALUE DOSSIER (caller-supplied — verify against the controlled evidence/model
systems before acting):
{request_text}

{wiki_context}

Produce a review with:

## Comparator appropriateness
- Each comparator and whether it fits the decision problem / target market

## Endpoint relevance
- Each endpoint and whether it is patient-relevant or a justified surrogate

## Extrapolation validity
- Each model extrapolation/assumption and whether the evidence supports it

## Model transparency and evidence fit
- Whether assumptions are sourced and the model structure is justified

## Gaps and recommendations
- Specific, closeable gaps (which comparator, which endpoint, which assumption)

## Claims
- Specific factual claims about the dossier that ground the review
"""

_REVISION_PROMPT = """\
Revise the HEOR value-dossier review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact comparator, endpoint, or model assumption
from the supplied dossier; do not assert one not in the input.
"""


@dataclass
class HEORDossierRequest:
    """Structured input for the HEOR value-dossier review workflow."""

    product_description: str
    """Generic product category and indication."""

    value_proposition: str
    """The economic and clinical value claim."""

    comparators: str
    """Relevant comparators for the decision problem."""

    clinical_evidence_summary: str
    """Trials / endpoints underpinning the value claim."""

    economic_model_summary: str
    """Cost-effectiveness / budget-impact model and key assumptions."""

    endpoints_used: str
    """Which endpoints are used — final vs surrogate."""

    extrapolation_assumptions: str
    """Survival / time-horizon extrapolation assumptions."""

    target_audience: str
    """Payer / HTA body / formulary committee."""

    def to_prompt_text(self) -> str:
        cap = _MAX_FIELD_CHARS
        return "\n".join([
            f"Product description: {self.product_description[:cap]}",
            f"Value proposition: {self.value_proposition[:cap]}",
            f"Comparators: {self.comparators[:cap]}",
            f"Clinical evidence summary: {self.clinical_evidence_summary[:cap]}",
            f"Economic model summary: {self.economic_model_summary[:cap]}",
            f"Endpoints used: {self.endpoints_used[:cap]}",
            f"Extrapolation assumptions: {self.extrapolation_assumptions[:cap]}",
            f"Target audience: {self.target_audience[:cap]}",
        ])


_FLAG_HEADERS: tuple[str, ...] = (
    "COMPARATOR FLAGS:",
    "ENDPOINT-RELEVANCE FLAGS:",
    "EXTRAPOLATION FLAGS:",
)


class HEORDossierWorkflow(BaseWorkflow):
    """
    Adversarial HEOR value-dossier review: executor structures the value argument
    → reviewer challenges an inappropriate comparator, an unjustified surrogate
    endpoint, and an over-optimistic model extrapolation → iterate.

    Convergence gate:
        score ≥ threshold
        AND zero COMPARATOR FLAGS
        AND zero ENDPOINT-RELEVANCE FLAGS
        AND zero EXTRAPOLATION FLAGS

    No reviewer veto — value-dossier corrections are reversible.
    """

    async def run(  # type: ignore[override]
        self,
        request: HEORDossierRequest,
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
                criteria=_HEOR_REVIEW_CRITERIA,
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

        heor_checklist = self._build_heor_checklist(request, accumulated)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "product_description": sanitize_for_prompt(
                    request.product_description, max_chars=200
                ),
                "comparator_flags": list(dict.fromkeys(accumulated["COMPARATOR FLAGS:"])),
                "endpoint_relevance_flags": list(
                    dict.fromkeys(accumulated["ENDPOINT-RELEVANCE FLAGS:"])
                ),
                "extrapolation_flags": list(
                    dict.fromkeys(accumulated["EXTRAPOLATION FLAGS:"])
                ),
                "heor_checklist": heor_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    @staticmethod
    def _format_flag_section(current: dict[str, list[str]]) -> str:
        if not any(current.values()):
            return ""
        banner = {
            "COMPARATOR FLAGS:": (
                "⚠️  COMPARATOR FLAGS (name the inappropriate or missing comparator "
                "for the decision problem / market):"
            ),
            "ENDPOINT-RELEVANCE FLAGS:": (
                "⚠️  ENDPOINT-RELEVANCE FLAGS (name the surrogate used where a "
                "patient-relevant final endpoint is required, without justification):"
            ),
            "EXTRAPOLATION FLAGS:": (
                "⚠️  EXTRAPOLATION FLAGS (name the model assumption/extrapolation the "
                "evidence does not support):"
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
    def _build_heor_checklist(
        request: HEORDossierRequest,
        accumulated: dict[str, list[str]],
    ) -> list[str]:
        checklist: list[str] = ["[OWNER: HEOR / Market Access]"]
        if accumulated["COMPARATOR FLAGS:"]:
            checklist.append(
                "[ ] Replace every flagged comparator with the current standard of "
                "care for the decision problem"
            )
        if accumulated["ENDPOINT-RELEVANCE FLAGS:"]:
            checklist.append(
                "[ ] Justify or replace every flagged surrogate endpoint with a "
                "patient-relevant final endpoint"
            )
        if accumulated["EXTRAPOLATION FLAGS:"]:
            checklist.append(
                "[ ] Support or revise every flagged model extrapolation against "
                "the evidence"
            )
        checklist.extend([
            "[ ] Confirm every comparator fits the decision problem and target market",
            "[ ] Confirm each endpoint is patient-relevant or a justified surrogate",
            "[ ] Confirm every model assumption is sourced and supported",
            "[ ] Obtain HEOR / Market Access sign-off before dossier submission",
        ])
        return checklist
