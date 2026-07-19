---
name: promo_checklist
description: MLR committee sign-off checklist for a promotional-material review; includes outstanding flags and veto do-not-release row
inputs:
  - veto_reason
  - off_label_flags
  - fair_balance_flags
  - substantiation_flags
  - material_type
  - target_audience
---

[OWNER: MLR Committee (Medical + Legal + Regulatory)]

Before the promotional material is released:
- [ ] If REVIEWER VETO issued — do not release the material; escalate to the MLR committee (likely FDA enforcement/untitled-letter exposure) before any distribution. Veto directive: {veto_reason}
- [ ] Remove or restrict every off-label claim to the approved indication for: {material_type}
- [ ] Add risk information with comparable prominence to the benefit claims
- [ ] Attach adequate substantiation for each efficacy / comparative claim, or remove it
- [ ] Obtain MLR sign-off before the material is released

Target audience reviewed: {target_audience}

Outstanding flags:
- Off-label: {off_label_flags}
- Fair-balance: {fair_balance_flags}
- Substantiation: {substantiation_flags}
