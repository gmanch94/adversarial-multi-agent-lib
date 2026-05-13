---
name: demand_stockout_risk
description: Evaluate stockout vs. overstock risk for a retail replenishment decision
inputs: [sku, product_category, current_inventory, lead_time_days, forecast_units, order_quantity]
---
You are a supply chain risk analyst. Evaluate the risk balance for this replenishment decision.

SKU: {sku}
Category: {product_category}
Current inventory: {current_inventory}
Supplier lead time: {lead_time_days} days
4-week demand forecast: {forecast_units} units
Proposed order quantity: {order_quantity} units

Assess:
1. **Days of supply** — at the forecast run rate, how many days does current inventory cover?
2. **Stockout window** — if the order arrives on day (lead_time_days), will inventory run out before delivery?
3. **Post-order inventory** — projected on-hand after order arrives. Is it excessive for the category?
   (Dairy: max 10-14 days; Produce: max 3-5 days; Dry goods: max 30-45 days)
4. **Safety stock adequacy** — does the order recommendation include buffer for forecast error?

Output:
- Days of supply (current): X days
- Stockout risk: [High/Moderate/Low] — [reason]
- Overstock risk: [High/Moderate/Low] — [reason]
- Recommendation: [Increase order / Maintain / Reduce order] by ~N units, with justification
