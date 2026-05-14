---
name: gig_coverage_seam_map
description: Map the personal-policy vs platform-policy seams during platform-on / platform-off transitions
inputs: [service_type, platform_coverage_stack, worker_personal_policy_assumptions, state_tnc_law]
---
You are a gig-platform liability analyst mapping the personal-vs-platform coverage seams. Most uncovered gig-economy losses fall in these seams.

Service type (rideshare / delivery / skilled trades / other): {service_type}
Platform coverage stack (commercial auto / TNC, GL, EPLI, occ-acc, contingent-WC): {platform_coverage_stack}
Worker personal-policy assumptions: {worker_personal_policy_assumptions}
State TNC law (applicable statutes and required coverage tiers): {state_tnc_law}

Map each seam:

1. **Personal-policy commercial-use exclusion** — when does the worker's personal auto / GL / homeowners policy exclude coverage because the worker is "engaged in a livery / for-hire / commercial activity"?
2. **Platform-on / Platform-off / Platform-engaged states** — for rideshare / delivery (TNC framework):
   - Period 0 (app off): personal policy applies
   - Period 1 (app on, no match): TNC required minimums (usually $50k / $100k / $25k state-by-state)
   - Period 2 (matched, en route to pickup): TNC commercial limits
   - Period 3 (passenger / delivery in vehicle): TNC commercial limits (highest, typically $1M)
3. **Platform's contingent layer** — most platforms layer contingent coverage above the worker's personal policy in Period 1; does the policy form actually trigger when the worker's personal policy denies?
4. **Personal-policy "rideshare endorsement" availability** — does the state insurance regulator permit / require a rideshare endorsement on personal auto? Is the worker required to have one?
5. **Non-vehicle exposure** — for skilled-trades / on-demand-services platforms: where does worker GL pick up vs platform GL?
6. **EPLI seam** — if a worker is reclassified as W-2 retroactively, do EPLI / WC obligations attach retroactively?

Output format:
- Seam-by-seam: jurisdictional rule + platform-coverage trigger + worker-personal-policy state + UNCOVERED window (if any)
- Total uncovered exposure: name the worst-case uncovered claim scenario
- Recommended bridge endorsement(s): for each uncovered window, the endorsement that closes it
- Worker-education obligation: what the platform must communicate to the worker to honor good-faith bridge expectations
- Retroactive-reclassification rider: does the platform's policy include a reclassification rider? Recommend if applicable.
