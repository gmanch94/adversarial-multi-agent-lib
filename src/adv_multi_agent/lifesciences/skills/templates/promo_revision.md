---
name: promo_revision
description: Revision prompt for promotional-material MLR review; addresses OFF-LABEL FLAGS, FAIR-BALANCE FLAGS, SUBSTANTIATION FLAGS from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this promotional-material review. Address EVERY issue in the reviewer's
critique, especially any OFF-LABEL FLAGS, FAIR-BALANCE FLAGS, or SUBSTANTIATION
FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Claim-by-claim label check, Fair-balance
assessment, Substantiation and references, Comparative-claim check, Redline
recommendations, Claims).

For every OFF-LABEL FLAG: remove the claim or restrict it to the approved
indication, population, and dosing. Do not promote an off-label use.

For every FAIR-BALANCE FLAG: add risk / limitation information with prominence
comparable to the benefit claims. Do not de-emphasise or omit material risk.

For every SUBSTANTIATION FLAG: attach an adequate citation that supports the
claim, or remove the claim. Do not leave an efficacy or comparative claim
unsupported.
