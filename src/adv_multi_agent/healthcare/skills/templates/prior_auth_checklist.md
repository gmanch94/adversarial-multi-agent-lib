---
name: prior_auth_checklist
description: Pre-determination checklist for the prior authorization nurse / case manager
inputs:
  - medical_necessity_flags
  - coverage_flags
  - documentation_flags
---
Owner: Prior Authorization Nurse / Case Manager.

Before issuing any approval or denial:
- [ ] Confirm member eligibility and benefit at the date of service requested
- [ ] Verify cited clinical guideline (InterQual / MCG) effective version
- [ ] Document medical-necessity rationale citing specific guideline criteria
- [ ] Route denials to medical director for physician review before issuance
- [ ] Notify provider of decision within plan turnaround time
      (urgent 72h / standard 5 business days)

Outstanding flags:
- Medical necessity: {medical_necessity_flags}
- Coverage: {coverage_flags}
- Documentation: {documentation_flags}
