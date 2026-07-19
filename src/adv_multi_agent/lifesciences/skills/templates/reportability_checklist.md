---
name: reportability_checklist
description: Post-market Surveillance / Vigilance officer sign-off checklist for a device-reportability determination; includes outstanding flags and veto initiate-report row
inputs:
  - veto_reason
  - reportability_flags
  - serious_injury_flags
  - malfunction_trend_flags
  - device_identifier
  - market_regions
---

[OWNER: Post-market Surveillance / Vigilance Officer]

Before the reportability determination is closed:
- [ ] If REVIEWER VETO issued — a 'non-reportable' determination is actually reportable; escalate to the Vigilance officer and initiate the report within the statutory clock. Veto directive: {veto_reason}
- [ ] Re-apply the reporting definition and state the statutory clock for: {device_identifier}
- [ ] Re-grade the outcome against the serious-injury definition
- [ ] Evaluate the malfunction trend against prior similar events
- [ ] File within the statutory clock for each affected market region
- [ ] Obtain Vigilance officer sign-off before the determination is closed

Market regions reviewed: {market_regions}

Outstanding flags:
- Reportability: {reportability_flags}
- Serious-injury: {serious_injury_flags}
- Malfunction-trend: {malfunction_trend_flags}
