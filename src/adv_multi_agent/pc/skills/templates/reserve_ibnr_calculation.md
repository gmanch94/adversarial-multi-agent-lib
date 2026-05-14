---
name: reserve_ibnr_calculation
description: Apply an IBNR / loss-development uplift to a case reserve with stated methodology
inputs: [line_of_business, case_reserve, severity_trend, claim_age_months]
---
You are an actuarial analyst applying IBNR uplift to a case reserve. State the methodology explicitly so a senior actuary can verify it.

Line of business: {line_of_business}
Case reserve (indemnity + defence): {case_reserve}
Severity trend (annualised %): {severity_trend}
Claim age (months from loss date): {claim_age_months}

Compute:
1. **Loss-development factor (LDF)** — apply the conventional LDF for this line at this claim-age tier (state the LDF or LDF range you applied).
2. **Severity-trend uplift** — multiply by (1 + severity_trend) ^ (months_to_settle / 12). State the months_to_settle assumption.
3. **Combined uplift %** — show the math.
4. **Uplifted reserve $** — case_reserve × combined uplift.

Output format:
- LDF applied: X.X (justification: line + age tier)
- Severity-trend uplift: Y.Y% (over Z months to settle)
- Combined uplift: A.A%
- Uplifted reserve: $N
- Methodology note: one paragraph defensible against Schedule P review.
- Sensitivity: state how the uplifted reserve changes if LDF moves ±10%.
