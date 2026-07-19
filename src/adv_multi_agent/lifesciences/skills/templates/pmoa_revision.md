---
name: pmoa_revision
description: Revise a combination-product PMOA analysis using reviewer feedback; re-derive the PMOA from the mechanism and each constituent's contribution per flag
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the combination-product PMOA analysis based on reviewer critique.

ORIGINAL ANALYSIS:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
For any flagged item: re-derive the PMOA from the therapeutic mechanism and each
constituent's contribution; do not assert a center/pathway that does not follow
from the PMOA.
