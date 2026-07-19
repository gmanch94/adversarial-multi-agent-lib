---
name: fieldaction_checklist
description: Recall Committee / Chief Quality Officer sign-off checklist for a field-action classification; includes outstanding flags and veto do-not-under-scope row
inputs:
  - veto_reason
  - recall_class_flags
  - correction_removal_flags
  - health_hazard_flags
  - action_type
  - distribution_scope
---

[OWNER: Recall Committee / Chief Quality Officer]

Before the field action proceeds:
- [ ] If REVIEWER VETO issued — a recall-class downgrade or 'not reportable' call leaves patients exposed; escalate to the Recall committee / CQO and do not under-scope the action. Veto directive: {veto_reason}
- [ ] Re-derive the recall class from the health hazard for: {action_type}
- [ ] Apply the 21 CFR 806 correction-vs-removal reportability test
- [ ] Re-state the health-hazard evaluation (probability/severity/population) without understating
- [ ] Confirm the affected lot / distribution scope is complete for the root cause
- [ ] Obtain Recall committee sign-off before the field action proceeds

Distribution scope reviewed: {distribution_scope}

Outstanding flags:
- Recall-class: {recall_class_flags}
- Correction-removal: {correction_removal_flags}
- Health-hazard: {health_hazard_flags}
