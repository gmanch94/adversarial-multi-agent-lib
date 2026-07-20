---
name: ccds_revision
description: Revision pass for a CCDS safety label-change review; addresses reviewer SAFETY-SIGNAL / REGIONAL-DIVERGENCE / IMPLEMENTATION-CLOCK flags
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise this CCDS safety label-change review. Address EVERY issue in the reviewer's
critique, especially any SAFETY-SIGNAL FLAGS, REGIONAL-DIVERGENCE FLAGS, or
IMPLEMENTATION-CLOCK FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SAFETY-SIGNAL flag: convey the established signal faithfully; do not understate it.
⚠️  For any REGIONAL-DIVERGENCE flag: reconcile the region or justify the divergence.
⚠️  For any IMPLEMENTATION-CLOCK flag: correct the plan to meet the mandatory clock.
