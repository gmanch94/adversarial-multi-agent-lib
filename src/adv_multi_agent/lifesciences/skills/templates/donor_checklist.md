---
name: donor_checklist
description: QA / Tissue-Safety sign-off checklist for a donor-eligibility determination review; includes outstanding flags and veto do-not-release row
inputs:
  - veto_reason
  - screening_gap_flags
  - testing_gap_flags
  - ineligible_release_flags
  - donation_type
---

[OWNER: Quality Assurance / Tissue-Safety (Donor-Eligibility) Officer]

Before releasing the allogeneic product ({donation_type}):
- [ ] If REVIEWER VETO issued — do not release the allogeneic product; escalate to Quality Assurance / Tissue-safety and complete screening / testing before any release. Veto directive: {veto_reason}
- [ ] Confirm risk-factor screening is complete and correctly interpreted
- [ ] Confirm communicable-disease testing is present, correct method, correctly read
- [ ] Confirm any urgent-medical-need path is documented as such, not routine eligibility
- [ ] Obtain Quality Assurance / Tissue-safety sign-off before any release

Outstanding flags:
- Screening-gap: {screening_gap_flags}
- Testing-gap: {testing_gap_flags}
- Ineligible-release: {ineligible_release_flags}
