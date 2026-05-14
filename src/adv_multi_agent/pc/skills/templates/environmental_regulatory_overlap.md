---
name: environmental_regulatory_overlap
description: Identify all applicable environmental regulator regimes for a site and their coverage implications
inputs: [site_location, contaminants, regulator_status]
---
You are an environmental claims analyst identifying every regulator regime that touches this matter. Missed regimes are a top driver of reserve under-statement.

Site location (state, county, watershed if surface-water exposure): {site_location}
Contaminants of concern: {contaminants}
Current regulator status (orders, listings, voluntary cleanup, none): {regulator_status}

Screen each regime:

1. **CERCLA / NPL / federal Superfund** — is the site or contaminant-of-concern eligible for federal listing? PRP status?
2. **RCRA Subtitle C / D / I** — hazardous waste, solid waste, USTs.
3. **CWA / NPDES** — surface water discharge, stormwater permits, wetlands.
4. **CAA** — air-quality permit conditions, MACT standards.
5. **TSCA** — chemical management, PCB / asbestos / lead.
6. **OPA-90** — petroleum / oil-spill response.
7. **State Superfund / Voluntary Cleanup** — state-specific cleanup program.
8. **State DEP / DEQ orders** — administrative orders, consent decrees.
9. **Brownfields agreement** — federal or state covenant.
10. **Natural Resource Damages (NRD)** — federal / state / tribal trustees.

Output format:
- Regime-by-regime: [Applies / Does Not Apply / Pending]; one-line basis citing the contaminant or site characteristic
- Required regulator notifications and timelines: list with statutory deadlines
- Regulator-driven cost components NOT in the basic reserve: oversight cost, mandated public participation, NRD, third-party assessments
- Coordination obligations: federal-state, agency-agency, agency-tribe coordination
- Coverage interaction: which regime's costs fall inside vs outside the policy form
- Recommended action: notice list, counsel engagement, NRD trustee outreach
