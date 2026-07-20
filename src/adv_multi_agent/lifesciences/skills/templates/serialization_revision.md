---
name: serialization_revision
description: Revise a serialization / DSCSA traceability review using reviewer feedback; cite the exact aggregation tier, EPCIS event, or saleable return for every flag
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise the serialization / DSCSA traceability review based on reviewer critique.

ORIGINAL REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
For any flagged item: cite the exact aggregation tier, EPCIS event, or saleable
return from the supplied configuration; do not assert one not in the input.
