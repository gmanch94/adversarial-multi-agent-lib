"""
Workflow — Parole Assessment (Teaching / Research Example)

Demonstrates how to adapt the ARIS adversarial pattern to high-stakes
decision-support. Two cross-family AI models iterate on a parole case
assessment: the executor synthesizes evidence; the reviewer challenges
quality, balance, and—critically—checks for demographic proxy bias.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
This is a teaching example showing the PATTERN. A real system requires:

    PRODUCTION_GAPS
    ───────────────
    1. Disparate-impact auditing — validate recommendations against
       historical decisions for demographic parity (COMPAS/PATTERN
       precedent). Include regular statistical audits.

    2. Calibrated risk scores — map qualitative assessments to actuarial
       base rates; do not present 0–10 AI scores as objective measures.

    3. Court-admissible explanations — every claim traceable to a specific
       source document with citation. No opaque chain-of-thought.

    4. Dedicated third-model bias auditor — a separate model (different
       family from both executor and reviewer) whose ONLY job is demographic
       proxy detection. This workflow folds bias detection into the reviewer;
       a production system should separate it.

    5. Demographic blind evaluation — redact race, gender, ZIP code, school
       name, and socioeconomic indicators BEFORE the executor sees the case.
       Human reviewers re-introduce context after the AI pass.

    6. Jurisdiction compliance check — AI output must be validated against
       applicable statutes before release to the board.

    7. Human approval gate — the board member must explicitly acknowledge
       reading the brief before it enters the record. The system must not
       auto-deliver to downstream processes.

See docs/decisions.md for the design decision log.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import sanitize_for_prompt
from ...core.workflow import BaseWorkflow, WorkflowResult

# ---------------------------------------------------------------------------
# Disclaimer — mandatory on all output
# ---------------------------------------------------------------------------

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated brief is not a parole decision. "
    "A qualified human parole board member must review all evidence independently "
    "and make the final determination. AI output must never be the sole or primary "
    "basis for liberty deprivations. See PRODUCTION_GAPS in parole.py."
)

# ---------------------------------------------------------------------------
# Input dataclass
# ---------------------------------------------------------------------------


@dataclass
class ParoleCase:
    """
    Structured case input for the parole assessment workflow.

    All fields are free-text strings to accommodate the variety of real
    court and facility document formats. The executor interprets them;
    the reviewer challenges that interpretation.

    Fields deliberately avoid protected characteristics (race, gender,
    national origin). Demographic information should be redacted before
    constructing a ParoleCase for production use.
    """

    case_id: str
    """Anonymised case identifier. Do not use full name in production."""

    offense_description: str
    """Nature of offense, charges, conviction details from court record."""

    sentence_imposed: str
    """Original sentence length as stated in the sentencing order."""

    time_served: str
    """Time already served, including any credits."""

    in_custody_conduct: str
    """
    Disciplinary incidents (type, frequency, recency) and positive conduct
    (rule compliance, work assignments, peer relationships) from facility
    records.
    """

    programs_completed: str
    """
    Educational programs (GED, college), vocational training, substance-abuse
    treatment, cognitive-behavioral therapy, and other rehabilitative activities.
    Include completion dates and provider names where available.
    """

    psychological_assessment: str
    """
    Summary of the most recent psychological evaluation. Include assessment
    date, key findings, and any diagnoses relevant to risk or treatment.
    """

    reentry_plan: str
    """
    Post-release plan: housing (address and landlord contact), employment
    (employer and position), community support persons, supervision officer
    contact, and any specialized programming (e.g., halfway house, IOP).
    """

    victim_statement: str = ""
    """Victim impact statement, if provided and permitted for inclusion."""

    external_risk_score: str = ""
    """
    Actuarial risk score (e.g., ORAS-PT, LSI-R) if administered. Include
    instrument name, score, risk tier, and assessment date. Leave blank if
    not available — the workflow will note this as an evidence gap.
    """

    def to_prompt_text(self) -> str:
        """Format case fields as structured text for prompt injection."""
        parts = [
            f"Case ID: {self.case_id}",
            f"Offense: {self.offense_description}",
            f"Sentence imposed: {self.sentence_imposed}",
            f"Time served: {self.time_served}",
            f"In-custody conduct: {self.in_custody_conduct}",
            f"Programs completed: {self.programs_completed}",
            f"Psychological assessment: {self.psychological_assessment}",
            f"Reentry plan: {self.reentry_plan}",
        ]
        if self.victim_statement:
            parts.append(f"Victim statement: {self.victim_statement}")
        if self.external_risk_score:
            parts.append(f"External risk score: {self.external_risk_score}")
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Review criteria — dual mandate: quality + bias audit
# ---------------------------------------------------------------------------

_PAROLE_REVIEW_CRITERIA = """\
Evaluate this parole assessment brief on five dimensions. Score each 0–10.

1. BALANCE (30 %)
   Does the assessment give honest, proportionate weight to BOTH the risk
   factors AND the rehabilitation evidence? Does it avoid advocating for
   a particular outcome? Penalise one-sided framing in either direction.

2. EVIDENCE GROUNDING (25 %)
   Is every risk or rehabilitation claim grounded in the specific case
   evidence provided? Penalise claims that rely on statistical patterns,
   stereotypes, or reasoning that applies to a class of offenders rather
   than this individual.

3. BIAS AUDIT (25 %) — CRITICAL
   Carefully check whether any reasoning uses a demographic proxy as a
   risk factor. Flag and deduct points for:
     • Neighbourhood or ZIP code used as risk signal
     • School quality or educational background inferred as risk
     • Family history patterns (beyond the individual's own record)
     • Socioeconomic status as a proxy for recidivism risk
     • Any characteristic statistically correlated with race, gender,
       national origin, religion, or other protected class
   Such reasoning is legally impermissible in most jurisdictions and
   produces the COMPAS-class errors this system must avoid.
   If bias is found, list each instance under "BIAS FLAGS:" as bullets.

4. COMPLETENESS (10 %)
   Are significant evidence gaps explicitly identified? Does the assessment
   note what information is absent and how it limits confidence?

5. ACTIONABILITY (10 %)
   Are the proposed conditions specific, proportionate to identified risks,
   and practically enforceable by a parole officer?

Overall score = weighted average of the above.
Score ≥ 7.5 means the brief is ready for human board review.
Score < 7.5 requires revision.

End your review with:
  Overall score: X/10
  Key issues: [bullet list]
  BIAS FLAGS: [bullet list, or "None detected"]
"""

# ---------------------------------------------------------------------------
# Prompt templates
# ---------------------------------------------------------------------------

_INITIAL_PROMPT = """\
You are preparing a balanced parole assessment brief for a human parole board.
You have NO stake in the outcome. Your job is accuracy and completeness, not
advocacy. The board will make the final decision — you inform it.

⚠️  BASE ALL RISK ASSESSMENTS ON INDIVIDUAL BEHAVIOUR AND CASE EVIDENCE ONLY.
Do NOT use neighbourhood, school attended, family history, socioeconomic status,
or any demographic characteristic as a risk factor. These are legally
impermissible proxies for protected characteristics.

CASE FILE:
{case_text}

{wiki_context}
Produce a structured assessment with exactly these sections:

## Risk Analysis
Identify specific risk factors from the case evidence: nature and severity of
the offense, in-custody disciplinary incidents (type, frequency, recency),
any prior supervision violations, substance-use history directly evidenced in
the record. Do NOT cite demographics or socioeconomic proxies.

## Rehabilitation Evidence
What concrete steps has this individual taken? List each program completed,
education credential earned, or documented behavioural change. Assess the
credibility and recency of each evidence item.

## Reentry Plan Assessment
Evaluate the post-release plan: housing stability, employment prospects,
community support network, and supervision plan quality. Note gaps and risks.

## Advisory Recommendation
Grant / Conditional Grant / Deny — with specific reasoning tied to the
evidence above.
THIS IS ADVISORY ONLY. The parole board makes the final decision.

## Conditions If Granted
Specific, proportionate, enforceable conditions that address each identified
risk. Each condition should be actionable by a parole officer.

## Evidence Gaps
Information missing from the case file that would materially improve this
assessment. Note the impact of each gap on confidence.

## Claims
One factual claim per line. Format: "[Source: <case field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this parole assessment brief. Address EVERY issue identified in the
reviewer's critique, especially any bias flags.

PREVIOUS ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}
{bias_section}
{wiki_context}

Revise the brief using the same section structure.

⚠️  For any flagged bias: REMOVE the flagged reasoning entirely and replace it
with case-specific behavioural evidence only. Do not rephrase demographic
reasoning — remove it.
"""


# ---------------------------------------------------------------------------
# Workflow
# ---------------------------------------------------------------------------


class ParoleAssessmentWorkflow(BaseWorkflow):
    """
    Adversarial parole assessment: executor drafts → reviewer challenges → iterate.

    Pattern adaptation highlights (teaching):
    ──────────────────────────────────────────
    1. Structured input (ParoleCase) instead of free-text task string.
       This forces the caller to think about what evidence they actually have.

    2. Dual-mandate reviewer criteria — the reviewer scores quality AND
       performs an explicit bias audit. Two responsibilities, one model.
       (A production system would use a third, independent model for the
       bias check — see PRODUCTION_GAPS in the module docstring.)

    3. Bias flags are extracted from the reviewer's critique and fed back
       explicitly to the executor in the revision prompt, with instructions
       to REMOVE (not rephrase) the offending reasoning.

    4. Convergence gate: the loop only converges when score ≥ threshold
       AND the reviewer reports zero bias flags. A biased-but-polished
       brief does not converge.

    5. Output is a WorkflowResult whose .output field contains the full
       advisory brief with a mandatory disclaimer appended. The board
       checklist in metadata surfaces the human verification steps.

    Args:
        config: Standard Config. Cross-family provider pairing strongly
                recommended (ARIS §3.2) — Gemini executor + GPT-4o reviewer
                or equivalent. Same-family pairs emit a UserWarning.
    """

    async def run(  # type: ignore[override]
        self,
        case: ParoleCase,
        **_: Any,
    ) -> WorkflowResult:
        """
        Run the adversarial assessment loop for a parole case.

        Args:
            case: Structured case input. Demographic proxies should be
                  redacted before passing (see ParoleCase docstring).

        Returns:
            WorkflowResult:
              output       — Full advisory brief (markdown) + disclaimer.
              final_score  — Reviewer score on the last round (0–10).
              converged    — True if score ≥ threshold AND no bias flags.
              metadata     — Dict with keys:
                               case_id, recommendation, bias_flags,
                               board_checklist, disclaimer, ledger_summary.
        """
        config = self.config
        case_text = sanitize_for_prompt(case.to_prompt_text(), max_chars=8000)

        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_bias_flags: list[str] = []
        all_bias_flags: list[str] = []
        max_claim_chars = getattr(config, "max_claim_text_chars", 1000)

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    case_text=case_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                bias_section = ""
                if current_bias_flags:
                    flags_text = "\n".join(
                        f"  - {f}" for f in current_bias_flags
                    )
                    bias_section = (
                        f"\n⚠️  BIAS FLAGS (must be removed, not rephrased):\n"
                        f"{flags_text}\n"
                    )
                prompt = _REVISION_PROMPT.format(
                    previous=sanitize_for_prompt(output, max_chars=12000),
                    score=f"{score:.1f}",
                    critique=sanitize_for_prompt(
                        review.critique, max_chars=4000
                    ),
                    suggestions="\n".join(
                        f"- {sanitize_for_prompt(s, max_chars=500)}"
                        for s in review.suggestions
                    ),
                    bias_section=bias_section,
                    wiki_context=wiki_ctx,
                )

            output = await self.executor.run(prompt, context="")
            self._register_claims(output, round_num, max_claim_chars)

            review = await self.reviewer.review(
                output,
                criteria=_PAROLE_REVIEW_CRITERIA,
            )
            score = review.score

            current_bias_flags = self._extract_bias_flags(review.critique)
            all_bias_flags.extend(current_bias_flags)

            self.wiki.add_feedback(
                sanitize_for_prompt(
                    review.critique,
                    max_chars=config.max_wiki_body_chars,
                ),
                round_num=round_num,
                score=score,
            )

            # Converge only when score threshold met AND no remaining bias flags.
            # A polished-but-biased brief must continue iterating.
            if review.approved and not current_bias_flags:
                converged = True
                break

        recommendation = self._extract_recommendation(output)
        board_checklist = self._build_board_checklist(
            case, all_bias_flags
        )

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "case_id": case.case_id,
                "recommendation": recommendation,
                "bias_flags": list(dict.fromkeys(all_bias_flags)),  # dedup, preserve order
                "board_checklist": board_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _register_claims(
        self,
        output: str,
        round_num: int,
        max_chars: int,
    ) -> None:
        """Parse '## Claims' section and register each line in the ledger."""
        if "## Claims" not in output:
            return
        claims_section = output.split("## Claims", 1)[1]
        existing = {c.text for c in self.ledger.all()}
        for raw_line in claims_section.splitlines():
            line = raw_line.strip().lstrip("-•").strip()
            if not line:
                continue
            if len(line) > max_chars:
                line = line[:max_chars]
            if line in existing:
                continue
            try:
                self.ledger.add(line, round_num=round_num)
                existing.add(line)
            except ValueError:
                continue

    @staticmethod
    def _extract_bias_flags(critique: str) -> list[str]:
        """
        Extract bias flags from reviewer critique.

        The reviewer is instructed to list bias flags under a 'BIAS FLAGS:'
        heading. This method extracts those lines. Returns empty list if the
        reviewer reports 'None detected' or the section is absent.
        """
        if "BIAS FLAGS:" not in critique:
            return []
        section = critique.split("BIAS FLAGS:", 1)[1]
        flags: list[str] = []
        for line in section.splitlines():
            stripped = line.strip().lstrip("-•*").strip()
            if not stripped:
                continue
            # Stop at the next heading or summary line
            if stripped.lower().startswith(("overall", "key issues", "#")):
                break
            if stripped.lower() in ("none detected", "none", "n/a"):
                return []
            flags.append(stripped)
        return flags

    @staticmethod
    def _extract_recommendation(output: str) -> str:
        """Extract the advisory recommendation line from the executor output."""
        marker = "## Advisory Recommendation"
        if marker not in output:
            return "See full brief"
        section = output.split(marker, 1)[1].split("##", 1)[0].strip()
        for line in section.splitlines():
            stripped = line.strip()
            if stripped:
                return stripped[:200]
        return "See full brief"

    @staticmethod
    def _build_board_checklist(
        case: ParoleCase,
        bias_flags: list[str],
    ) -> list[str]:
        """
        Build the human verification checklist for the parole board.

        This checklist exists to remind the human reviewer that the AI
        brief is one structured input, not a determination. Every item
        requires a human action.
        """
        checklist: list[str] = []

        if bias_flags:
            checklist.append(
                f"[ ] ⚠️  BIAS FLAGS DETECTED ({len(bias_flags)} instance(s)) — "
                "review ALL flagged reasoning before using this brief; consider "
                "requesting a human-only reassessment"
            )

        checklist.extend([
            f"[ ] Verify completeness of case file for {case.case_id}",
            "[ ] Cross-check Risk Analysis claims against original facility reports",
            "[ ] Confirm Rehabilitation Evidence: request program completion certificates",
            "[ ] Verify Reentry Plan contacts independently (call housing provider, employer)",
            "[ ] Review psychological assessment summary with a licensed clinician",
            "[ ] Confirm victim notification procedures were followed",
            "[ ] Apply independent judgment to the Advisory Recommendation — "
                "the board is NOT bound by AI output",
            "[ ] Record your reasoning independently of this brief",
            "[ ] Sign off: AI brief reviewed; final decision is the board's alone",
        ])
        return checklist
