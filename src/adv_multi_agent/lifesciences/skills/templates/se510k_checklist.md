---
name: se510k_checklist
description: Regulatory Affairs sign-off checklist for a substantial-equivalence 510(k) rationale; includes outstanding flags and veto do-not-assert row
inputs:
  - veto_reason
  - predicate_mismatch_flags
  - indication_creep_flags
  - technology_delta_flags
  - subject_device_description
  - candidate_predicates
---

[OWNER: Regulatory Affairs Lead]

Before any 510(k) premarket notification is submitted:
- [ ] If REVIEWER VETO issued — do not assert substantial equivalence; escalate to Regulatory Affairs and consider a De Novo / PMA pathway before any submission. Veto directive: {veto_reason}
- [ ] Confirm the predicate's intended use matches the subject device: {subject_device_description}
- [ ] Narrow the subject indications-for-use to the predicate's cleared scope
- [ ] Resolve each technological difference with supporting performance data
- [ ] Obtain Regulatory Affairs sign-off before any 510(k) submission

Candidate predicate(s) reviewed: {candidate_predicates}

Outstanding flags:
- Predicate-mismatch: {predicate_mismatch_flags}
- Indication-creep: {indication_creep_flags}
- Technology-delta: {technology_delta_flags}
