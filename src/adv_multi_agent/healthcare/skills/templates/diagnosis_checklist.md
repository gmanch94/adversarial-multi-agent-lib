---
name: diagnosis_checklist
description: Pre-submission checklist for the certified coder to clear before any claim is submitted
inputs:
  - accuracy_flags
  - compliance_flags
  - specificity_flags
---

Owner: Health Information Manager / Certified Coder (CCS, CPC).

Before claim submission:
- [ ] Verify every flagged code change against primary encounter documentation
- [ ] Confirm cited ICD-10-CM / AHA Coding Clinic / payer LCD references resolve to current effective-date guidance
- [ ] Resolve specificity gaps by querying the provider for additional documentation, not by guessing
- [ ] Document audit rationale in the coding compliance log (RAC / OIG audit trail)
- [ ] Submit claim only after credentialed coder sign-off

Outstanding flags:
- Accuracy: {accuracy_flags}
- Compliance: {compliance_flags}
- Specificity: {specificity_flags}
