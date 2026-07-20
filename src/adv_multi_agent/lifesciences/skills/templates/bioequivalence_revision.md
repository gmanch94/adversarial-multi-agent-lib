---
name: bioequivalence_revision
description: Revision pass for a bioequivalence assessment; addresses reviewer PK-BOUNDARY / STUDY-DESIGN / WAIVER-JUSTIFICATION flags
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise this bioequivalence assessment. Address EVERY issue in the reviewer's
critique, especially any PK-BOUNDARY FLAGS, STUDY-DESIGN FLAGS, or
WAIVER-JUSTIFICATION FLAGS.

PREVIOUS ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any PK-BOUNDARY flag: do not treat a CI outside the limits as equivalent.
⚠️  For any STUDY-DESIGN flag: correct the design element for this product.
⚠️  For any WAIVER-JUSTIFICATION flag: justify or withdraw the waiver/limit.
