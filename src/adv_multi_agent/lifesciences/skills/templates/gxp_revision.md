---
name: gxp_revision
description: Revision pass for a GxP data-integrity assessment; addresses reviewer ALCOA / AUDIT-TRAIL / ATTRIBUTION flags against the supplied evidence
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the GxP data-integrity assessment based on reviewer critique.

ORIGINAL ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact record and the ALCOA+ attribute,
audit-trail gap, or attribution failure from the supplied evidence; do not
assert an attribute state the evidence does not support.
