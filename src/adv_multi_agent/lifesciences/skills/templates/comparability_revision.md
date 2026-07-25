---
name: comparability_revision
description: Revision prompt for a CGT post-change comparability review; addresses PROCESS-DELTA, ANALYTICAL-GAP, and CLINICAL-BRIDGE flags from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this post-change comparability review. Address EVERY issue in the
reviewer's critique, especially any PROCESS-DELTA FLAGS, ANALYTICAL-GAP FLAGS, or
CLINICAL-BRIDGE FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Process-change impact, Analytical
comparability, Clinical bridging, Risk assessment, Comparability conclusion,
Claims).

For every PROCESS-DELTA FLAG: address the change's impact on the named critical
quality attribute, or acknowledge it is uncovered.

For every ANALYTICAL-GAP FLAG: extend the analytical panel to support the
comparability conclusion, or acknowledge the gap.

For every CLINICAL-BRIDGE FLAG: provide the clinical bridging that resolves the
residual uncertainty, or acknowledge new clinical data are required.
