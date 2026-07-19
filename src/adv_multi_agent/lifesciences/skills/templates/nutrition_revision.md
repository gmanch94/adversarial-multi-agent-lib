---
name: nutrition_revision
description: Revise a nutrition label-claim review using reviewer feedback; cite the specific dossier evidence, nutrient requirement, or allergen source per flag
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the nutrition label-claim review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
For any flagged item: cite the specific dossier evidence / nutrient requirement /
allergen source; do not assert substantiation absent from the supplied dossier
summary.
