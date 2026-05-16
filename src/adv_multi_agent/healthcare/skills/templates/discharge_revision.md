---
name: discharge_revision
description: Revise discharge plan assessment using reviewer feedback; remove or ground every flagged claim
inputs:
  - previous
  - critique
  - flag_section
---

Revise the prior discharge plan assessment:

ORIGINAL:
{previous}

REVIEWER CRITIQUE:
{critique}

{flag_section}

For every flagged item: REMOVE the unsupported claim or replace it with
a citation to specific language in the submitted patient data.
Do not rephrase. Maintain the same section structure
(## Readmission risk, ## Care gaps, ## Social-determinant context,
## Discharge plan revisions, ## Claims).
