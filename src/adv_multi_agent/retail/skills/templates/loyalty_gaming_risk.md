---
name: loyalty_gaming_risk
description: Enumerate plausible gaming / exploit paths against a loyalty offer (basket-splitting, multi-account, threshold-bumping, return abuse, gift-card laundering) and propose mitigations per path
inputs: [offer_proposal, historical_response, gaming_risk]
---
You are an offer-fraud analyst. Enumerate plausible exploits and propose
a detection / prevention mitigation per path. Be specific — "monitor for
fraud" is not a mitigation.

Offer proposal: {offer_proposal}
Historical response (esp. prior gaming patterns): {historical_response}
Caller-identified gaming risks: {gaming_risk}

Enumerate at least five exploit paths. For each:

1. **Path name** (e.g. "basket-splitting to clear threshold cheaper")
2. **Mechanic** — exactly what the customer does
3. **Expected value to the customer** — rough $ benefit per attempt
4. **Detectability** — what telemetry would catch this within 24 h
5. **Mitigation** — a concrete control:
   • Hard control: offer mechanics change (e.g. eligibility filter,
     per-household cap, return-window restriction)
   • Soft control: monitoring + manual review trigger
   State which type. Soft-only mitigations REQUIRE telemetry instrumented
   pre-launch, not "we'll add this later".

Common paths to include:
- Basket-splitting (multiple smaller transactions vs one large)
- Multi-account (same household creating second loyalty account)
- Threshold-bumping (adding low-margin items to clear a threshold then
  returning them)
- Gift-card laundering (purchasing gift cards on promo, then redeeming
  for non-discounted items)
- Coupon-stacking (combining with other concurrent offers in unintended ways)

Output format:
- Path table: name → mechanic → EV → detectability → mitigation type +
  description
- GAMING FLAGS to surface to reviewer: [bullet list of paths with no
  mitigation or soft-only mitigation but no telemetry committed]
- Pre-launch instrumentation checklist: [bullet list]
