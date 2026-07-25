---
name: rmat_checklist
description: Regulatory Strategy sign-off checklist for an RMAT designation eligibility assessment; includes outstanding EVIDENCE-STRETCH, SERIOUS-CONDITION, and UNMET-NEED flags
inputs:
  - evidence_stretch_flags
  - serious_condition_flags
  - unmet_need_flags
  - product_description
---

[OWNER: Regulatory Strategy]

Before any RMAT designation request for: {product_description}
- [ ] Confirm the product qualifies as a regenerative-medicine therapy
- [ ] Confirm the preliminary clinical evidence credibly indicates potential to address the condition
- [ ] Confirm the unmet-need claim holds against the available-therapy landscape
- [ ] Obtain Regulatory Strategy sign-off before any designation request

Outstanding flags:
- Evidence-stretch: {evidence_stretch_flags}
- Serious-condition: {serious_condition_flags}
- Unmet-need: {unmet_need_flags}
