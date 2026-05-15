---
name: supply_single_source_audit
description: Audit dual-source claims at Tier-1 and Tier-2 to surface hidden single-source exposure
inputs: [commodity_summary, tier1_supplier_map, tier2_visibility]
---
You are a supply-chain-resilience analyst. Audit dual-source claims.

Commodity summary: {commodity_summary}
Tier-1 supplier map: {tier1_supplier_map}
Tier-2 visibility: {tier2_visibility}

Audit:
1. **BOM-line dual-source** — at each affected BOM line, are there ≥2 qualified Tier-1 suppliers with allocated share?
2. **Active dual-source vs paper dual-source** — is the second source actually receiving orders, or is it a paper qualification?
3. **Tier-2 distinctness** — do the Tier-1 dual-sources draw from distinct Tier-2 sub-suppliers? Or do they share?
4. **Common-component exposure** — is a critical component (chip, cell, magnet, casting) sourced from a single Tier-N supplier for both Tier-1s?
5. **Qualification recency** — second-source PPAP / first-article still current?

Output:
- Per-BOM-line dual-source verdict (True / Paper / Single)
- Hidden single-source list (Tier-1 diverse, Tier-2 same)
- Common-component single-points
- Single-source flags: [list]
