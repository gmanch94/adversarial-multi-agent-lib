---
name: assay_checklist
description: Diagnostics Regulatory + R&D sign-off checklist for IVD assay performance-claim review; includes outstanding flags and veto do-not-release row
inputs:
  - veto_reason
  - sensitivity_claim_flags
  - specificity_claim_flags
  - interference_flags
  - assay_description
  - claim_set
---

[OWNER: Diagnostics Regulatory + R&D]

Before any IVD label or IFU is released:
- [ ] If REVIEWER VETO issued — do not release the claim; escalate to Diagnostics Regulatory before any label is issued. Veto directive: {veto_reason}
- [ ] Re-state every performance claim within the study confidence interval for: {assay_description}
- [ ] Restrict each claimed matrix/population to the tested interferents and cross-reactants
- [ ] Confirm the CLSI EP study design supports the released claim set
- [ ] Obtain Diagnostics Regulatory sign-off before any label is released

Claim set reviewed: {claim_set}

Outstanding flags:
- Sensitivity-claim: {sensitivity_claim_flags}
- Specificity-claim: {specificity_claim_flags}
- Interference: {interference_flags}
