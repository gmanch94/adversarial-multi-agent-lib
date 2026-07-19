---
name: cmo_revision
description: Revision pass for a CMO / CDMO qualification review; addresses reviewer GMP-GAP / DATA-INTEGRITY / CAPACITY flags against the supplied evidence
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the CMO / CDMO qualification review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact audit observation, data-integrity
weakness, or capacity gap from the supplied evidence; do not assert a fact the
evidence does not show.
