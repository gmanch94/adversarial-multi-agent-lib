---
name: design_revision
description: Revise a design-control traceability audit using reviewer feedback; cite the exact missing input-output-evidence link for every flag
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the design-control traceability audit based on reviewer critique.

ORIGINAL AUDIT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
For any flagged item: cite the exact missing input↔output↔evidence link from the
DHF inputs; do not assert a link that is not in the supplied evidence.
