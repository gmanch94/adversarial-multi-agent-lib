---
name: sterility_revision
description: Revision pass for a sterility assurance review; addresses reviewer SAL / BIOBURDEN / VALIDATION-GAP flags
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise this sterility assurance review. Address EVERY issue in the reviewer's
critique, especially any SAL FLAGS, BIOBURDEN FLAGS, or VALIDATION-GAP FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any SAL flag: do not assert a SAL the validation/routine data do not support.
⚠️  For any BIOBURDEN flag: state the bioburden vs the validated limit.
⚠️  For any VALIDATION-GAP flag: name the missing/expired validation element.
