---
name: supplier_geo_concentration_check
description: Check whether adding a supplier creates geographic / sub-tier concentration risk at the commodity level
inputs: [supplier_summary, sub_tier_and_geographic, capacity_and_continuity]
---
You are a supply-chain-risk analyst. Check geographic-concentration impact of qualifying this supplier.

Supplier summary: {supplier_summary}
Sub-tier and geographic: {sub_tier_and_geographic}
Capacity and continuity: {capacity_and_continuity}

Check:
1. **OEM commodity exposure** — what share of OEM's spend for this commodity goes to this supplier's region?
2. **Cluster overlap** — do other OEM suppliers cluster in the same region / industrial park / shared logistics?
3. **Tier-2 distinctness** — does this supplier's Tier-2 set overlap with other Tier-1s?
4. **Sanctions / export-control screen** — OFAC SDN, BIS Entity List, EU consolidated, UN. Current?
5. **Political / natural-hazard overlay** — typhoon, seismic, water-stress, civil-unrest, regulatory regime.
6. **Logistics-route fragility** — common chokepoint exposure (Panama, Suez, Malacca, Hormuz).

Output:
- Concentration tier: [Low / Moderate / High]
- Sub-tier overlap with other suppliers: [list]
- Sanctions / export-control screen: [Clean / Refresh required / Match]
- Resilience-action recommendation
- Geo-concentration flags: [list]
