---
name: assay_revision
description: Revision prompt for IVD assay performance-claim review; addresses SENSITIVITY-CLAIM FLAGS, SPECIFICITY-CLAIM FLAGS, INTERFERENCE FLAGS from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this assay performance-claim review. Address EVERY issue in the reviewer's
critique, especially any SENSITIVITY-CLAIM FLAGS, SPECIFICITY-CLAIM FLAGS, or
INTERFERENCE FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Claim-by-claim data mapping,
Sensitivity assessment, Specificity assessment, Interference and cross-reactivity,
Recommended claim set, Claims).

For every SENSITIVITY-CLAIM or SPECIFICITY-CLAIM FLAG: re-state the claim within
the study confidence interval and n, or remove it. Do not assert a point estimate
that ignores the lower CI bound.

For every INTERFERENCE FLAG: restrict the claimed matrix/population to the
interferents and cross-reactants actually tested. Do not claim a matrix whose
interferents were not evaluated.
