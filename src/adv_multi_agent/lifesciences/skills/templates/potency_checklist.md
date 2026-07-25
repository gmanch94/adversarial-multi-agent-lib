---
name: potency_checklist
description: CMC + Quality Engineering sign-off checklist for a CGT potency-assay adequacy review; includes outstanding flags and veto do-not-release row
inputs:
  - veto_reason
  - moa_linkage_flags
  - lot_release_claim_flags
  - assay_validation_flags
  - product_description
---

[OWNER: CMC / Analytical Development + Quality Engineering]

Before the potency assay supports lot release of: {product_description}
- [ ] If REVIEWER VETO issued — do not release on this potency assay; escalate to CMC / Analytical Development + QE and requalify the assay before any lot disposition. Veto directive: {veto_reason}
- [ ] Confirm the assay readout is linked to the mechanism of action
- [ ] Confirm the acceptance criteria support the lot-release claim
- [ ] Confirm the assay is validated and stability-indicating
- [ ] Obtain CMC + QE sign-off before any lot disposition

Outstanding flags:
- MoA-linkage: {moa_linkage_flags}
- Lot-release-claim: {lot_release_claim_flags}
- Assay-validation: {assay_validation_flags}
