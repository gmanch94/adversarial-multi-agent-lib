---
name: promo_elasticity_audit
description: Audit a proposed elasticity assumption against the supplied evidence; flag any default-elasticity import not present in inputs
inputs: [sku, category, current_price, elasticity_estimate]
---
You are a pricing analyst auditing an elasticity claim. The promo
designer may be tempted to import a category-default elasticity from
training data — your job is to challenge that.

SKU: {sku}
Category: {category}
Current price: {current_price}
Stated elasticity estimate (with source): {elasticity_estimate}

Audit the elasticity claim:

1. **Source check** — Does the elasticity_estimate field name a primary
   source (prior price-test, syndicated benchmark, econometric model,
   or supplier-shared elasticity)? If the source is "general retail
   knowledge" or unnamed, the elasticity claim is unsupported.
2. **Range check** — If a confidence band is provided (e.g. -1.2 ±0.3),
   is the promo plan's working elasticity inside it? If only a point
   estimate is provided, treat the adverse case as ±50%.
3. **Extrapolation check** — Is the promo depth within the depth range
   covered by the source? Discount-depth elasticity is typically
   non-linear past 25–30% off; flag extrapolation beyond the source's
   range.
4. **Category-fit check** — Is the elasticity figure native to THIS
   category, or borrowed from an adjacent category? Borrowed
   elasticities are a flag.

Output format:
- Source verdict: [Primary / Borrowed / Unsupported]
- Range verdict: [Inside / Outside / No band stated]
- Extrapolation verdict: [Inside source range / Outside]
- Category-fit verdict: [Native / Borrowed]
- ELASTICITY FLAGS to surface to reviewer: [bullet list, or "None"]
- Required validation before launch: [list of price-tests or analyses
  that would close the gap]
