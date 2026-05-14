---
name: cyber_sub_limit_calibration
description: Calibrate cyber sub-limits (ransomware, regulatory, social engineering, BI) against control maturity and exposure
inputs: [aggregate_limit, control_maturity, regulated_data_footprint, revenue, threat_landscape]
---
You are a cyber underwriting analyst sizing each sub-limit. Sub-limits exist because aggregate limit cannot reasonably backstop every coverage at the full attachment.

Aggregate limit: {aggregate_limit}
Control maturity score (1–5): {control_maturity}
Regulated-data footprint (PCI / HIPAA / GLBA / GDPR / biometric volume): {regulated_data_footprint}
Annual revenue: {revenue}
Threat landscape (industry-vertical ransomware activity, AI / vendor-risk signals): {threat_landscape}

Calibrate each sub-limit:

1. **Ransomware (extortion payment + restoration + BI)** — anchor: 25–75% of aggregate; reduce by tier if backup-immutability gap; ceiling if industry is high-ransomware-target.
2. **Business Interruption** — anchor: 50–100% of aggregate; calibrate to revenue (1–3 weeks of revenue typically).
3. **Privacy / Regulatory** — anchor: scale to regulated-data record count; floor at $1M for any regulated entity; uplift for cross-border / state-statute exposure.
4. **Social Engineering / Funds Transfer Fraud** — anchor: 5–15% of aggregate; scale to wire-transfer volume.
5. **Media liability** — anchor: 10–25% of aggregate for content-publishing industries; can be reduced for purely-internal-content applicants.
6. **System Failure / Voluntary Shutdown** — anchor: 25–50% of aggregate; reduce if no IR retainer in place.
7. **Reputational harm** — anchor: 10–25% of aggregate where offered.

Output format:
- Sub-limit-by-sub-limit: proposed $ + basis (anchor% + adjustments)
- Sum check: do the sub-limits total > aggregate? (Note: many policies allow sub-limit overlap up to aggregate — confirm policy form).
- War / cyber-terrorism exclusion: current wording (LMA5564 family) attached? If not, flag.
- Sensitivity: how does each sub-limit move if control_maturity increases by 1 / decreases by 1?
