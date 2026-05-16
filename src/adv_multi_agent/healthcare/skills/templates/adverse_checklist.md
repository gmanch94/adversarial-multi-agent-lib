---
name: adverse_checklist
description: Pharmacovigilance officer sign-off checklist for adverse-event triage; includes outstanding flags and veto expedited-filing row
inputs:
  - veto_reason
  - severity_flags
  - causality_flags
  - regulatory_flags
  - product_name
  - outcome
---

[OWNER: Pharmacovigilance Officer / Drug Safety Scientist]

Before any regulatory filing or case closure:
- [ ] If REVIEWER VETO issued — initiate MedWatch / EudraVigilance expedited filing within regulatory clock. Veto directive: {veto_reason}
- [ ] Verify MedDRA PT/SOC coding for event against current MedDRA browser for: {product_name}
- [ ] Confirm causality assessment via WHO-UMC or Naranjo with documented criteria
- [ ] Confirm labeling status against current USPI / SmPC / sponsor safety database
- [ ] Notify sponsor / SUSAR-relevant parties per ICH E2A if clinical trial
- [ ] File final report and document in safety database

Outcome reported: {outcome}

Outstanding flags:
- Severity: {severity_flags}
- Causality: {causality_flags}
- Regulatory: {regulatory_flags}
