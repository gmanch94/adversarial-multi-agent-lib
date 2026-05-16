---
name: diagnosis_revision
description: Revise diagnosis-code audit using reviewer feedback; remove or ground every flagged code claim
inputs:
  - previous
  - critique
  - flag_section
---

Revise the prior diagnosis-code audit:

ORIGINAL:
{previous}

REVIEWER CRITIQUE:
{critique}

{flag_section}

For every flagged item: REMOVE the unsupported code claim or replace it with a citation to specific language in the encounter documentation. Do not rephrase. Maintain the same section structure.
