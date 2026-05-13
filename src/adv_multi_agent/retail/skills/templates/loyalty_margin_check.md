---
name: loyalty_margin_check
description: Audit projected contribution margin for a loyalty offer against the stated floor, factoring discount depth, cannibalization, free-rider redemption, and fulfilment lift
inputs: [offer_proposal, margin_floor, historical_response, competing_offers]
---
You are a finance analyst. Audit projected per-unit contribution margin
against the stated floor. Be conservative — assume free-rider redemption
unless the input data explicitly bounds it.

Offer proposal: {offer_proposal}
Margin floor (per-unit, stated): {margin_floor}
Historical response data: {historical_response}
Competing offers (concurrent / competitor): {competing_offers}

Compute margin under three scenarios:

1. **Pure-incremental** (no free riders, no cannibalization): naive
   upside case. State it for context.
2. **Realistic** (historical free-rider %, expected cannibalization on
   adjacent SKUs, normal fulfilment cost): the planning case.
3. **Adverse** (high free-rider %, cannibalization on the household's
   highest-margin SKU, fulfilment lift from new-channel adoption): the
   stress case.

For each scenario:
- Discount cost per redemption
- Cannibalization cost (lost margin on substituted SKUs)
- Fulfilment cost delta
- Free-rider cost (discounts to customers who would have purchased
  anyway)
- Net per-unit contribution margin
- Pass / fail vs floor

Output format:
- Three-scenario table: scenario → discount → cannibalization → fulfilment
  → free-rider → net margin → verdict
- Margin-floor verdict: [Pass / Fail] at the realistic scenario
- MARGIN FLAGS to surface to reviewer: [bullet list, or "None"]
- Recommended discount cap to keep the floor in adverse scenario: [value]
