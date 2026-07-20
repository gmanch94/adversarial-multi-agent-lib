---
name: cybersec_revision
description: Revise a premarket device cybersecurity review using reviewer feedback; cite the exact attack surface, SBOM component, or un-patchable component for every flag
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the premarket device cybersecurity review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
For any flagged item: cite the exact attack surface, SBOM component, or
un-patchable component from the supplied package; do not assert one not in the input.
