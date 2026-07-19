---
name: stability_revision
description: Revision pass for a stability / shelf-life review; addresses reviewer EXTRAPOLATION / TREND / SPEC-EXCEEDANCE flags against the supplied data
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the stability / shelf-life review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged item: cite the exact attribute, timepoint, or batch from the
supplied stability data; do not assert a trend or extrapolation the data lack.
