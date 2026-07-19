---
name: csv_revision
description: Revision pass for a computer system validation review; addresses reviewer INTENDED-USE / TRACE-GAP / TEST-EVIDENCE flags against the supplied package
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the computer system validation review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact requirement, test, or evidence gap from
the supplied validation package; do not assert a link the evidence does not show.
