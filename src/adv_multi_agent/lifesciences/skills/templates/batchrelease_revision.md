---
name: batchrelease_revision
description: Revision pass for a batch-release deviation disposition; addresses reviewer CRITICALITY / IMPACT-ASSESSMENT / RELEASE-RISK flags
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise this batch-release deviation disposition. Address EVERY issue in the
reviewer's critique, especially any CRITICALITY FLAGS, IMPACT-ASSESSMENT FLAGS,
or RELEASE-RISK FLAGS.

PREVIOUS DISPOSITION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any CRITICALITY flag: re-classify the deviation against its CQA/safety impact.
⚠️  For any IMPACT-ASSESSMENT flag: identify every affected CQA.
⚠️  For any RELEASE-RISK flag: state and resolve the unresolved risk before release.
