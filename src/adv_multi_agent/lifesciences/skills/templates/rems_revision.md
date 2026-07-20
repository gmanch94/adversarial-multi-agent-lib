---
name: rems_revision
description: Revise a REMS design review using reviewer feedback; cite the exact risk-element-metric mismatch for every flag
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the REMS design review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
For any flagged item: cite the exact risk-element-metric mismatch from the
supplied design; do not assert a risk or element that is not in the input.
