---
name: fieldaction_revision
description: Revision prompt for a field-action classification; addresses RECALL-CLASS FLAGS, CORRECTION-REMOVAL FLAGS, HEALTH-HAZARD FLAGS from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this field-action classification. Address EVERY issue in the reviewer's
critique, especially any RECALL-CLASS FLAGS, CORRECTION-REMOVAL FLAGS, or
HEALTH-HAZARD FLAGS.

PREVIOUS CLASSIFICATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Problem and root cause, Health-hazard
evaluation, Recall classification, Correction vs removal reportability, Scope
(lots / distribution), Claims).

For every RECALL-CLASS FLAG: re-derive the recall class from the health hazard.
Do not downgrade a Class I hazard to a lower class.

For every CORRECTION-REMOVAL FLAG: apply the 21 CFR 806 reportability test. Do
not mislabel a reportable correction or removal as a non-reportable enhancement
or routine stock recovery.

For every HEALTH-HAZARD FLAG: re-state probability, severity, and affected
population without understating any.
