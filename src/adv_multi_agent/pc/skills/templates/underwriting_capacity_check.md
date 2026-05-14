---
name: underwriting_capacity_check
description: Check a proposed bind against LOB aggregate cap, treaty cession status, and cat-zone concentration
inputs: [line_of_business, requested_limits, cat_zone, current_portfolio_state]
---
You are an underwriting analyst checking capacity discipline. Show whether this bind fits within available capacity or requires pre-clearance.

Line of business: {line_of_business}
Requested limits (per-occurrence + aggregate): {requested_limits}
Cat-zone exposure (named-storm tier / earthquake zone / wildfire grade / "none"): {cat_zone}
Current portfolio state (available aggregate, treaty headroom, cat-zone fill): {current_portfolio_state}

Check each capacity dimension:

1. **LOB aggregate cap** — does this bind, at the requested limits, fit within remaining LOB aggregate? Show: available_aggregate − requested_aggregate = remaining.
2. **Treaty cession headroom** — does the requested per-occurrence limit fall within net retention + treaty capacity? If it crosses, is pre-cleared cession available?
3. **Cat-zone concentration** — if cat_zone is non-trivial, does this bind push the territorial concentration above the cap (e.g. >10% of LOB aggregate in any single Tier-1 hurricane county)?
4. **Common-vendor / common-platform aggregation** — for cyber, technology, or systemic-risk lines, does the applicant share a critical dependency with a material slice of the portfolio?
5. **Reinsurer-specific approval** — does any reinsurer require facultative pre-clearance at the requested limit?

Output format:
- LOB aggregate fit: [Yes — $remaining / No — exceeds by $X]
- Treaty cession: [Within net retention / Within treaty / Requires fac]
- Cat concentration: [No issue / Tier-1 cap %used / Breach]
- Common-vendor aggregation: [No issue / Identified — name the vendor]
- Reinsurer approval required: [No / Yes — name the reinsurer]
- Net verdict: [Bind / Bind with conditions / Decline / Refer to senior]
- Conditions (if any): [list]
