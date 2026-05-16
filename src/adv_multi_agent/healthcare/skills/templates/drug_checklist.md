---
name: drug_checklist
description: Clinical pharmacist sign-off checklist for drug-interaction review; includes outstanding flags and veto escalation row
inputs:
  - veto_reason
  - severity_flags
  - evidence_flags
  - contraindication_flags
  - new_medication
  - renal_function
  - hepatic_function
---

[OWNER: Clinical Pharmacist]

Before any dispensing or prescribing decision:
- [ ] If REVIEWER VETO issued — escalate to clinical pharmacist BEFORE any prescribing action. Veto directive: {veto_reason}
- [ ] Verify every flagged interaction against live Lexicomp / Micromedex monograph for: {new_medication}
- [ ] Confirm renal dose adjustments against validated calculator (Cockcroft-Gault; renal function: {renal_function})
- [ ] Confirm hepatic dose adjustments against validated calculator (Child-Pugh; hepatic function: {hepatic_function})
- [ ] Pharmacist sign-off in EHR before dispensing

Outstanding flags:
- Severity: {severity_flags}
- Evidence: {evidence_flags}
- Contraindication: {contraindication_flags}
