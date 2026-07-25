---
name: hctp_revision
description: Revision prompt for an HCT/P regulatory-tier classification; addresses MINIMAL-MANIPULATION, HOMOLOGOUS-USE, and TIER-CLASSIFICATION flags from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this HCT/P tier classification. Address EVERY issue in the reviewer's
critique, especially any MINIMAL-MANIPULATION FLAGS, HOMOLOGOUS-USE FLAGS, or
TIER-CLASSIFICATION FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Minimal manipulation, Homologous use,
Combination and systemic effect, Tier conclusion, Precedent, Claims).

For every MINIMAL-MANIPULATION FLAG: show processing keeps the relevant
characteristics unaltered, or acknowledge more-than-minimal manipulation (351).

For every HOMOLOGOUS-USE FLAG: show the use is homologous to the original basic
function, or acknowledge non-homologous use (351).

For every TIER-CLASSIFICATION FLAG: resolve the combination or systemic-effect
prong, or acknowledge the product is a 351 biologic requiring a BLA.
