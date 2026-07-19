---
name: pvsignal_revision
description: Revision pass for a pharmacovigilance signal evaluation; addresses reviewer SIGNAL-STRENGTH / CAUSALITY / LABELING-IMPACT flags
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise this pharmacovigilance signal evaluation. Address EVERY issue in the
reviewer's critique, especially any SIGNAL-STRENGTH FLAGS, CAUSALITY FLAGS, or
LABELING-IMPACT FLAGS.

PREVIOUS EVALUATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SIGNAL-STRENGTH flag: re-characterize the signal against the metrics.
⚠️  For any CAUSALITY flag: re-assess population-level causality with a basis.
⚠️  For any LABELING-IMPACT flag: reflect the labeling / regulatory implication in
the action.
