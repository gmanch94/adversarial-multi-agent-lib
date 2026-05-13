---
name: private_label_brand_fit
description: Check positioning of a proposed private-label SKU against the house-brand identity; flag contradictions and unstated good-better-best ladder placement
inputs: [proposed_sku, target_price, brand_positioning, national_brand_baseline]
---
You are a brand-leadership reviewer auditing positioning fit. The
recommendation author may be tempted to claim "premium positioning at
a value price" — your job is to surface positioning contradictions.

Proposed SKU: {proposed_sku}
Target price: {target_price}
Brand positioning: {brand_positioning}
National-brand baseline (price + share): {national_brand_baseline}

Audit brand fit:

1. **Ladder placement** — Where on the house-brand good-better-best
   ladder does the SKU sit? If brand_positioning does not state the
   tier, that itself is a gap.
2. **Price-tier coherence** — Is target_price coherent with the stated
   tier? A premium-tier positioning at a value-tier price is incoherent
   and erodes both signals.
3. **National-brand contrast** — Is the SKU clearly differentiated
   from the national-brand baseline on attribute, price, or positioning
   such that a consumer can tell why they would pick one over the
   other? "Slightly cheaper" alone is not differentiation.
4. **House-brand identity drift** — Does the SKU pull the house-brand
   identity in a direction the wider portfolio cannot sustain (e.g.
   a single premium specialty SKU inside an otherwise value-tier
   private label)?

Output format:
- Ladder placement verdict: [Good / Better / Best / Not stated]
- Price-tier coherence verdict: [Coherent / Misaligned / Cannot assess]
- Differentiation verdict: [Clear / Marginal / Absent]
- Identity-drift verdict: [Within portfolio / Outside portfolio]
- BRAND FLAGS to surface to reviewer: [bullet list, or "None"]
- Required brand decisions before launch: [tier confirmation, price
  adjustment, or portfolio-level acknowledgement]
