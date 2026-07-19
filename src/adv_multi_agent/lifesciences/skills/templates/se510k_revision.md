---
name: se510k_revision
description: Revision prompt for substantial-equivalence 510(k) rationale; addresses PREDICATE-MISMATCH FLAGS, INDICATION-CREEP FLAGS, TECHNOLOGY-DELTA FLAGS from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this substantial-equivalence rationale. Address EVERY issue in the
reviewer's critique, especially any PREDICATE-MISMATCH FLAGS, INDICATION-CREEP
FLAGS, or TECHNOLOGY-DELTA FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Predicate comparison, Intended use and
indications, Technological characteristics, Performance-data bridge,
Substantial-equivalence conclusion, Claims).

For every PREDICATE-MISMATCH FLAG: select a predicate that shares the subject's
intended use and device type, or acknowledge Not-Substantially-Equivalent. Do not
anchor to a predicate with a different intended use.

For every INDICATION-CREEP FLAG: narrow the subject indications-for-use to the
predicate's cleared scope. Do not claim indications broader than the predicate's.

For every TECHNOLOGY-DELTA FLAG: cite the performance data that resolves the new
question of safety or effectiveness, or acknowledge that the difference is
unresolved. Do not argue away a difference that raises a new question.
