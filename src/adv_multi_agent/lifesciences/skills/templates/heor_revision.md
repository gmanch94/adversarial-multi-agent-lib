---
name: heor_revision
description: Revise an HEOR value-dossier review using reviewer feedback; cite the exact comparator, endpoint, or model assumption for every flag
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the HEOR value-dossier review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
For any flagged item: cite the exact comparator, endpoint, or model assumption
from the supplied dossier; do not assert one not in the input.
