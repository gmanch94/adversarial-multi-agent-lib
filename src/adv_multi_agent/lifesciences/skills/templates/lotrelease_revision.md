---
name: lotrelease_revision
description: Revision prompt for a CGT lot-release specification audit; addresses SPEC-COVERAGE, SMALL-LOT, and SHELF-LIFE flags from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this lot-release specification audit based on reviewer critique. Address
EVERY issue, especially any SPEC-COVERAGE FLAGS, SMALL-LOT FLAGS, or SHELF-LIFE
FLAGS.

ORIGINAL AUDIT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Release-attribute coverage, Small-lot
sampling, Short-shelf-life release, Stability and out-of-specification handling,
Gaps and recommendations, Claims).

For every SPEC-COVERAGE FLAG: name the release-critical attribute lacking a
specification and add an adequate criterion; do not assert coverage not present.

For every SMALL-LOT FLAG: revise the sampling / test-consumption plan for the lot
size; do not ignore small-lot statistics.

For every SHELF-LIFE FLAG: justify or revise the rapid / real-time-release
decision for the short shelf life; do not release before result without validation.
