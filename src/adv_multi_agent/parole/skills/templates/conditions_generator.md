---
name: conditions_generator
description: Generate specific, proportionate, enforceable supervision conditions from identified risk factors
inputs: [risk_factors, reentry_plan_summary, supervision_level]
---
You are drafting supervision conditions for a human parole board. Every condition
must be specific, proportionate to a named risk, and enforceable by a parole officer.
Do not generate conditions for risks not present in the case evidence.

RISK FACTORS:
{risk_factors}

REENTRY PLAN SUMMARY:
{reentry_plan_summary}

SUPERVISION LEVEL: {supervision_level}

For each risk factor listed, propose one or more conditions following these rules:

- **Specific**: name the exact action, frequency, and responsible party.
  BAD: "Avoid substance use."
  GOOD: "Submit to random urinalysis testing at the direction of the supervising
  officer, no fewer than twice per month for the first 90 days."

- **Proportionate**: the burden of the condition must match the severity and
  recency of the risk. Do not impose high-burden conditions for low-severity
  or fully mitigated risks.

- **Enforceable**: the parole officer must be able to verify compliance without
  requiring court approval for each check. Avoid conditions that depend on
  third-party cooperation outside the officer's control.

- **Time-bounded where possible**: include a review date or an automatic
  expiry trigger (e.g. "for the first 180 days", "until completion of
  outpatient programme").

Format each condition as:
**Risk addressed**: [risk factor name]
**Condition**: [full condition text]
**Verification method**: [how the officer confirms compliance]
**Duration**: [fixed period or trigger for removal]

End with:
- **Standard conditions assumed**: list any jurisdiction-standard conditions
  (reporting, travel restrictions, no new offences) that apply regardless of
  individual risk and are not duplicated above.
- **Conditions requiring court order**: flag any proposed conditions that
  exceed standard parole authority and would require a separate court order.
