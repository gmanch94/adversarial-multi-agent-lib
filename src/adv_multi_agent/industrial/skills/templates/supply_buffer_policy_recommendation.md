---
name: supply_buffer_policy_recommendation
description: Recommend a strategic-buffer-inventory policy for a commodity given fragility and demand profile
inputs: [commodity_summary, inventory_and_buffer, lead_time_and_route_context]
---
You are an inventory-policy analyst. Recommend a strategic-buffer policy.

Commodity summary: {commodity_summary}
Inventory and buffer: {inventory_and_buffer}
Lead-time and route context: {lead_time_and_route_context}

Recommend:
1. **Buffer location** — supplier-managed / VMI / OEM warehouse / consignment / regional DC.
2. **Buffer sizing** — days-of-supply against demand variance + lead-time variance.
3. **Critical-spare cache** — single units of high-criticality / low-turn parts.
4. **Surge capacity** — air-freight allocation, emergency-buy authority.
5. **Cost vs availability trade-off** — opportunity cost of buffer cash vs cost of stockout.
6. **Trigger for buffer adjustment** — demand-signal threshold, lead-time-variance threshold, geopolitical-event trigger.

Output:
- Recommended buffer policy (location + sizing + triggers)
- Opportunity-cost estimate
- Stockout-risk reduction estimate
- Buffer-policy flags: [list]
