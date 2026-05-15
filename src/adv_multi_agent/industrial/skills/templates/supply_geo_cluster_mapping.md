---
name: supply_geo_cluster_mapping
description: Map geographic clustering of suppliers at country / region / industrial-park / shared-logistics level
inputs: [commodity_summary, geographic_context, tier1_supplier_map]
---
You are a geographic-risk analyst. Map supplier clustering beyond country level.

Commodity summary: {commodity_summary}
Geographic context: {geographic_context}
Tier-1 supplier map: {tier1_supplier_map}

Map at four scales:
1. **Country** — share of OEM commodity spend per country.
2. **Region / sub-national** — Suzhou + Kunshan area, Bavaria, Veneto, etc.
3. **Industrial park / cluster** — shared utilities (power, water, gas), shared logistics, shared labour pool.
4. **Single-site** — multiple suppliers in the same industrial park / building / port.

Overlay risks:
- **Natural hazard** — typhoon zone, seismic risk, water stress, flood plain.
- **Political / regulatory** — export-control regime, sanctions exposure, civil-unrest history.
- **Logistics chokepoint** — port-of-entry, canal, strait, single-rail-line dependency.
- **Energy** — grid reliability, dependency on single fuel source.

Output:
- Concentration map at each scale (spend % + supplier count)
- Risk overlay tier per cluster: [Low / Moderate / High]
- Geo-concentration flags: [list of high-risk clusters]
