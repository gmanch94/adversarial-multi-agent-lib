---
name: udi_revision
description: Revision pass for a UDI labeling review; addresses reviewer IDENTIFIER / GUDID-CONSISTENCY / PACKAGING-TIER flags against the supplied evidence
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the UDI labeling review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact identifier, database attribute, or
packaging tier from the supplied evidence; do not assert a value the evidence
does not show.
