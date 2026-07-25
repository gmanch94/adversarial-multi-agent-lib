---
name: vectorsafety_checklist
description: Biosafety / Nonclinical Safety sign-off checklist for a viral-vector genome-safety characterisation audit; includes outstanding RCR-RCL-RISK, INSERTIONAL-MUTAGENESIS, and ONCOGENICITY flags
inputs:
  - rcr_rcl_risk_flags
  - insertional_mutagenesis_flags
  - oncogenicity_flags
  - vector_description
---

[OWNER: Biosafety / Nonclinical Safety]

Before the vector-safety characterisation supports release:
- [ ] Confirm the RCR/RCL testing sensitivity is appropriate for the vector class: {vector_description}
- [ ] Confirm integration / copy-number data characterise insertional-mutagenesis risk
- [ ] Confirm the long-term-follow-up plan covers vector persistence and shedding
- [ ] Obtain Biosafety / Nonclinical Safety sign-off before release

Outstanding flags:
- RCR/RCL risk: {rcr_rcl_risk_flags}
- Insertional-mutagenesis: {insertional_mutagenesis_flags}
- Oncogenicity: {oncogenicity_flags}
