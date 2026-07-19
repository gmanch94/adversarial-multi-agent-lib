---
name: protocol_revision
description: Revision pass for a clinical protocol design review; addresses reviewer ENDPOINT / POWER / SAFETY-MONITORING flags
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise this clinical protocol design review. Address EVERY issue in the
reviewer's critique, especially any ENDPOINT FLAGS, POWER FLAGS, or
SAFETY-MONITORING FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any ENDPOINT flag: re-assess whether the endpoint supports the objective.
⚠️  For any POWER flag: re-justify the sample size and effect-size assumptions.
⚠️  For any SAFETY-MONITORING flag: strengthen the monitoring / stopping rules for
the known risk.
