---
name: discharge_checklist
description: Pre-discharge checklist for the discharge planner / social worker / care coordinator
inputs:
  - readmission_flags
  - care_gap_flags
  - social_determinant_flags
---

Owner: Discharge Planner / Social Worker / Care Coordinator.

Before signing the discharge order:
- [ ] Escalate post-acute follow-up intensity for high readmission risk;
      document LACE/HOSPITAL-equivalent rationale in the plan
- [ ] Confirm each named service, referral, and follow-up appointment
      is scheduled before discharge order is signed
- [ ] Verify transportation, housing, food security, and insurance barriers
      are concretely resolved — not assumed to self-resolve
- [ ] Confirm medication reconciliation completed and patient/caregiver
      education documented
- [ ] Confirm post-acute placement (SNF/IRF/home health/hospice)
      authorised by payer before discharge
- [ ] Schedule 48-hour phone follow-up and 7-day in-person/telehealth
      appointment for high-risk patients
- [ ] Document discharge summary in EHR and transmit to receiving
      provider / SNF / home health agency

Outstanding flags:
- Readmission: {readmission_flags}
- Care gaps: {care_gap_flags}
- Social determinants: {social_determinant_flags}
