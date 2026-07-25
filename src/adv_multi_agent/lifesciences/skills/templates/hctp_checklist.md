---
name: hctp_checklist
description: Regulatory Affairs (CBER pathway) sign-off checklist for an HCT/P regulatory-tier classification; includes outstanding flags and veto do-not-assert-361 row
inputs:
  - veto_reason
  - minimal_manipulation_flags
  - homologous_use_flags
  - tier_classification_flags
  - product_description
---

[OWNER: Regulatory Affairs Lead (CBER pathway)]

Before any regulatory-tier position is taken for: {product_description}
- [ ] If REVIEWER VETO issued — do not assert the 361 HCT/P tier; escalate to Regulatory Affairs (CBER pathway) and pursue the BLA (351) path. Veto directive: {veto_reason}
- [ ] Confirm all four 21 CFR 1271.10(a) prongs are satisfied before a 361 call
- [ ] Confirm the intended use is homologous to the original basic function
- [ ] Confirm no disqualifying combination or systemic effect
- [ ] Obtain Regulatory Affairs sign-off before any classification position

Outstanding flags:
- Minimal-manipulation: {minimal_manipulation_flags}
- Homologous-use: {homologous_use_flags}
- Tier-classification: {tier_classification_flags}
