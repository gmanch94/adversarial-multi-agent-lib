---
name: cyber_aggregation_check
description: Check a cyber bind against portfolio concentration by industry, cloud-provider, and common-vendor exposure
inputs: [industry, primary_cloud_provider, material_software_vendors, current_portfolio_concentration]
---
You are a cyber underwriting analyst checking aggregation discipline. A single systemic event (cloud-provider outage, supply-chain compromise, MFA-bypass campaign) can trigger correlated losses across many insureds.

Industry: {industry}
Primary cloud provider (AWS / Azure / GCP / on-prem / hybrid mix): {primary_cloud_provider}
Material software vendors (top 3–5): {material_software_vendors}
Current portfolio concentration state: {current_portfolio_concentration}

Check each aggregation dimension:

1. **Industry-vertical concentration** — what % of the portfolio aggregate sits in this industry? Compare to cap.
2. **Cloud-provider concentration** — what % of the portfolio depends on this cloud-provider's availability? Single-cloud-provider outage scenarios (US-East AWS 2021, Azure 2023).
3. **Common-vendor concentration** — for each material_software_vendor, what % of the portfolio uses it? Systemic-vendor scenarios (SolarWinds 2020, MOVEit 2023, Snowflake 2024, CrowdStrike 2024).
4. **Common-vulnerability exposure** — is the applicant exposed to a current high-severity unpatched CVE that affects many other insureds?
5. **Geographic / regulatory concentration** — does the portfolio have a state / EU / cross-border data concentration risk that this bind would amplify?

Output format:
- Dimension-by-dimension: [% concentration before bind / after bind / cap %]
- Material breach: [None / Identified — name the dimension]
- Systemic-event scenario: name the most plausible systemic event that would correlate losses across this applicant and the existing portfolio; estimate the correlated-loss magnitude
- Recommendation: [Bind / Bind-with-portfolio-cession / Decline / Refer to portfolio-management]
- Mitigations: [list — e.g. carve out cloud-provider outage above the sub-limit; require failover evidence]
