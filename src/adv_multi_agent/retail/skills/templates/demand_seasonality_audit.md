---
name: demand_seasonality_audit
description: Challenge seasonality assumptions in a demand forecast for a retail SKU
inputs: [product_category, seasonality_notes, upcoming_events, forecast_adjustments]
---
You are a demand planning auditor. Challenge the seasonality assumptions below.

Category: {product_category}
Stated seasonality notes: {seasonality_notes}
Upcoming events: {upcoming_events}
Forecast adjustments being challenged: {forecast_adjustments}

For each seasonal or event-based adjustment, evaluate:
1. **Is the adjustment direction correct?** (e.g. does summer actually lift dairy?)
2. **Is the magnitude justified?** State whether the stated % lift/drop is reasonable
3. **Is the timing correct?** Does the adjustment apply to the right forecast weeks?
4. **Is the evidence grounded in the inputs?** Flag adjustments that rely on general
   retail knowledge not present in the stated seasonality_notes or upcoming_events

Output as a bullet list per adjustment:
- Adjustment: [name]
  - Direction: [Correct/Questionable] — [reason]
  - Magnitude: [Justified/Overstated/Understated] — [reason]
  - Timing: [Correct/Off by N weeks]
  - Grounded: [Yes/No] — [flag text if No]
