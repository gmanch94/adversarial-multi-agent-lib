---
name: pmcf_revision
description: Revise a PMCF adequacy review using reviewer feedback; cite the exact under-evidenced claim, uncovered residual risk, or inadequate method for every flag
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the PMCF adequacy review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
For any flagged item: cite the exact under-evidenced claim, uncovered residual
risk, or inadequate method from the supplied plan; do not assert one not in the input.
