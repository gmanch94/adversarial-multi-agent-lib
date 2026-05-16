---
name: treatment_checklist
description: Attending physician checklist for treatment-plan review; includes veto escalation item, flag-class items, and standard pre-order-entry verification steps
inputs:
  - owner
  - veto_item
  - guideline_flag_item
  - contraindication_flag_item
  - risk_flag_item
---
[OWNER: Attending Physician]

{veto_item}
{guideline_flag_item}
{contraindication_flag_item}
{risk_flag_item}
[ ] Verify guideline citations resolve to current effective-date version
[ ] Confirm medication reconciliation against EHR med list
[ ] Pharmacy independent verification for new medication orders
[ ] Document risk discussion with patient in EHR
[ ] Order entry only after attending physician sign-off
