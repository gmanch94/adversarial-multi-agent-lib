---
name: coldchain_revision
description: Revision pass for a cold-chain excursion disposition; addresses reviewer STABILITY-IMPACT / DISPOSITION / EXCURSION-SCOPE flags
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise this cold-chain excursion disposition. Address EVERY issue in the
reviewer's critique, especially any STABILITY-IMPACT FLAGS, DISPOSITION FLAGS, or
EXCURSION-SCOPE FLAGS.

PREVIOUS DISPOSITION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any STABILITY-IMPACT flag: ground the impact in stability data and the MKT budget.
⚠️  For any DISPOSITION flag: align the disposition with the stability conclusion.
⚠️  For any EXCURSION-SCOPE flag: sum the cumulative excursion across all legs and lots.
