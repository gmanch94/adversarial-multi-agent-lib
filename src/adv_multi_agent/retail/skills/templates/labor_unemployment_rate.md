---
name: labor_unemployment_rate
description: Assess local unemployment rate as a staffing pool and wage pressure signal for retail labor scheduling
inputs: [store_id, unemployment_rate, staff_roster]
---
You are a retail HR analyst. Assess the labor market signal from local unemployment data.

Store: {store_id}
Local unemployment data: {unemployment_rate}
Current staff roster: {staff_roster}

Assess:
1. **Staffing pool** — does the local rate suggest it is easy or difficult to find replacement
   or additional staff quickly? (High unemployment → easier; low → harder)
2. **Turnover risk** — does the trend suggest staff are likely to leave for other opportunities?
   (Falling unemployment, tight market → higher turnover risk)
3. **Wage pressure** — does the market suggest current wage rates are above, at, or below
   market? High tightness may require above-market offers for open roles.
4. **Scheduling implication** — does the labor market signal warrant any change to how the
   schedule is built? (e.g. build in more cross-training flexibility; reduce reliance on PT
   staff who may leave)

Output:
- Labor pool availability: [Ample/Moderate/Tight]
- Turnover risk: [Low/Moderate/High]
- Wage pressure: [Below market/At market/Above market pressure]
- Scheduling implication: [one actionable sentence, or "No near-term implication"]
