"""
Parole Assessment — Example (Teaching / Research)

Demonstrates how to adapt the ARIS adversarial multi-agent pattern to
high-stakes decision support using ParoleAssessmentWorkflow.

Design pattern highlights shown here:
  1. Cross-family provider pairing (Gemini executor + GPT-4o reviewer)
     prevents echo-chamber effects — the two models have different failure
     modes and genuine adversarial pressure results.
  2. Dual-mandate reviewer criteria: quality/balance AND explicit bias audit.
  3. Convergence gate: loop continues until score threshold met AND zero
     bias flags remain in the reviewer's critique.
  4. Output is an advisory brief with a mandatory disclaimer — never a verdict.
  5. ClaimLedger registers every factual assertion for auditability.

Required environment variables:
  GEMINI_API_KEY   — Google AI Studio key for Gemini 2.5 Pro executor
  OPENAI_API_KEY   — OpenAI key for GPT-4o reviewer
  ANTHROPIC_API_KEY is NOT required for this configuration.

Usage:
  pip install 'adv-multi-agent[gemini]'
  GEMINI_API_KEY=... OPENAI_API_KEY=... python examples/parole_assessment.py

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
    See parole.py module docstring for the PRODUCTION_GAPS checklist.
    This example uses a synthetic, fictional case for illustration.
"""
from __future__ import annotations

import asyncio
import textwrap

from adv_multi_agent.core.config import Config, EffortLevel, ExecutorProvider, ReviewerProvider
from adv_multi_agent.workflows.parole import ParoleAssessmentWorkflow, ParoleCase

# ---------------------------------------------------------------------------
# Synthetic case — fictional, for illustration only
# ---------------------------------------------------------------------------
#
# Note on redaction: in a real system you would redact race, gender, ZIP code,
# school name, and socioeconomic identifiers before constructing this object.
# The fields below use behaviour-only language to demonstrate the pattern.

CASE = ParoleCase(
    case_id="CASE-2024-0847",
    offense_description=(
        "Convicted of second-degree burglary (residential). Entered an unoccupied "
        "dwelling and removed electronics. No violence, no weapons, no injury to "
        "persons. First felony conviction. Prior record: one misdemeanour disorderly "
        "conduct (2019, dismissed)."
    ),
    sentence_imposed="4 years (48 months)",
    time_served=(
        "36 months (75 %). Eligible for parole at 24 months; this is second hearing. "
        "Good-time credit of 90 days accrued."
    ),
    in_custody_conduct=(
        "Disciplinary record: two written warnings in year one (noise complaint, "
        "failure to report for work assignment). No incidents in the past 22 months. "
        "Work assignment: facility kitchen, supervisor notes describe punctuality and "
        "cooperative attitude. Peer conflict mediation: completed as respondent in "
        "month 8; no repeat incidents."
    ),
    programs_completed=(
        "Cognitive Behavioural Intervention for Substance Abuse (CBISA) — completed "
        "month 14, 24-session course, voluntary enrolment. "
        "GED — earned month 20 (no prior high-school diploma). "
        "Vocational: Forklift Operator certification — completed month 28, "
        "state-accredited, employer-ready certificate. "
        "Victim Empathy Workshop — 8-session course, completed month 32, facilitator "
        "notes describe active, reflective participation."
    ),
    psychological_assessment=(
        "Assessment conducted month 30 by licensed psychologist. Diagnoses: mild "
        "substance-use disorder (cannabis), currently in remission. No diagnoses of "
        "antisocial personality or psychopathy. PCL-R score: 6/40 (low range). "
        "Clinician notes: individual demonstrates perspective-taking growth since "
        "initial assessment at intake (month 2). Recommends continued outpatient "
        "substance-use counselling post-release."
    ),
    reentry_plan=(
        "Housing: confirmed room in licensed transitional housing facility (Sunrise "
        "Transitional Housing, 412 Oak St, Springfield); lease signed, 12-month "
        "commitment, facility manager contact: M. Torres, 555-0142. "
        "Employment: conditional offer letter from Springfield Logistics LLC for "
        "forklift operator position, contingent on parole approval; HR contact: "
        "R. Patel, 555-0198. "
        "Support: weekly check-ins with parole officer assigned (Officer Kim, "
        "District 4). Sponsor identified through NA programme (monthly contact). "
        "Outpatient substance-use counselling: enrolled at Community Health Centre, "
        "weekly sessions, first appointment scheduled."
    ),
    victim_statement=(
        "Victim submitted written statement. States property loss was fully covered "
        "by insurance. Expresses concern about reoffending but does not oppose parole "
        "provided supervision conditions are in place. Does not request hearing."
    ),
    external_risk_score=(
        "ORAS-PT administered month 31. Total score: 14/45 (Low-Moderate risk tier). "
        "Domain breakdown: Criminal History 3, Education/Employment 2, "
        "Family/Social 2, Substance Abuse 4, Leisure/Recreation 1, "
        "Companions 1, Attitudes/Orientation 1. "
        "Instrument: Ohio Risk Assessment System — Pretrial Tool, adapted for "
        "reentry. Score validated by certified assessor."
    ),
)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main() -> None:
    # Cross-family pairing: Gemini executor + GPT-4o reviewer.
    # This is the recommended configuration for adversarial pressure.
    # Swap executor_provider=ExecutorProvider.ANTHROPIC if you only have
    # an Anthropic key (adds anthropic_api_key requirement).
    config = Config(
        executor_provider=ExecutorProvider.GEMINI,
        reviewer_provider=ReviewerProvider.OPENAI,
        effort=EffortLevel.HIGH,
        max_review_rounds=4,        # allow up to 4 adversarial rounds
        score_threshold=7.5,        # brief must score ≥ 7.5 to converge
        workspace_dir="parole_workspace",
    )

    print("=" * 70)
    print("PAROLE ASSESSMENT — ADVERSARIAL MULTI-AGENT PATTERN")
    print("=" * 70)
    print(f"Case: {CASE.case_id}")
    print(f"Executor: {config.executor_provider.value} ({config.gemini_executor_model})")
    print(f"Reviewer: {config.reviewer_provider.value} ({config.reviewer_model})")
    print(f"Max rounds: {config.max_review_rounds}  |  Threshold: {config.score_threshold}/10")
    print()
    print("⚠️  TEACHING EXAMPLE — NOT FOR PRODUCTION DEPLOYMENT")
    print("    See parole.py → PRODUCTION_GAPS for deployment checklist.")
    print()

    workflow = ParoleAssessmentWorkflow(config)
    result = await workflow.run(case=CASE)

    # ------------------------------------------------------------------
    # Print results
    # ------------------------------------------------------------------

    print("=" * 70)
    print(f"ROUNDS COMPLETED: {result.rounds}")
    print(f"FINAL SCORE: {result.final_score:.1f}/10")
    print(f"CONVERGED: {result.converged}")
    print()

    bias_flags = result.metadata.get("bias_flags", [])
    if bias_flags:
        print(f"⚠️  BIAS FLAGS DETECTED ({len(bias_flags)}):")
        for flag in bias_flags:
            print(f"   • {flag}")
    else:
        print("✓ No bias flags detected in final brief")
    print()

    print(f"ADVISORY RECOMMENDATION: {result.metadata.get('recommendation', 'N/A')}")
    print()

    print("-" * 70)
    print("BOARD VERIFICATION CHECKLIST:")
    for item in result.metadata.get("board_checklist", []):
        print(f"  {item}")
    print()

    print("-" * 70)
    print("CLAIM LEDGER SUMMARY:")
    summary = result.metadata.get("ledger_summary", {})
    for status, count in summary.items():
        print(f"  {status}: {count}")
    print()

    print("=" * 70)
    print("FULL ADVISORY BRIEF:")
    print("=" * 70)
    print()
    # Wrap long lines for terminal readability
    for line in result.output.splitlines():
        if len(line) > 100:
            print(textwrap.fill(line, width=100))
        else:
            print(line)


if __name__ == "__main__":
    asyncio.run(main())
