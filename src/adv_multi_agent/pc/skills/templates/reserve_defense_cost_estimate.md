---
name: reserve_defense_cost_estimate
description: Estimate defence-cost reserve with stated methodology (percentage, hourly, or capped fee)
inputs: [line_of_business, indemnity_reserve, complexity_tier, expected_duration_months]
---
You are a claims analyst sizing the defence-cost reserve component. Pick exactly one methodology and justify the choice.

Line of business: {line_of_business}
Indemnity reserve: {indemnity_reserve}
Complexity tier (Routine / Moderate / Complex / Cat-class): {complexity_tier}
Expected duration to closure (months): {expected_duration_months}

Pick ONE methodology:

**Methodology A — Percentage of indemnity (default for routine claims):**
- Routine: 15–25% of indemnity
- Moderate: 25–40%
- Complex: 40–60%
- Cat-class: 60–100%+
State the percentage applied and justify.

**Methodology B — Hourly × expected hours (default for fee-cap-absent specialty lines):**
- State the panel-counsel hourly rate range applied.
- State the expected hours by phase (pleadings, discovery, expert, trial, appeal).
- Show the math.

**Methodology C — Capped fee (default when a panel agreement caps fees by claim tier):**
- State the cap and the tier criterion.

Output format:
- Methodology: [A / B / C]
- Defence-cost reserve: $N
- Show the math: [percentage × indemnity] OR [hours × rate] OR [cap]
- Justification: one paragraph defensible against Schedule P review.
- Sensitivity: state how the reserve changes if duration extends by 6 months OR if claim escalates one complexity tier.
