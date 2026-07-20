---
name: medinfo_revision
description: Revision pass for a medical-information response review; addresses reviewer OFF-LABEL / BALANCE / EVIDENCE-LEVEL flags
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---

Revise this medical-information response review. Address EVERY issue in the
reviewer's critique, especially any OFF-LABEL FLAGS, BALANCE FLAGS, or
EVIDENCE-LEVEL FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any OFF-LABEL flag: keep the response reactive and non-promotional; do not promote an off-label use.
⚠️  For any BALANCE flag: present the corresponding risk/limitation alongside efficacy.
⚠️  For any EVIDENCE-LEVEL flag: state the claim no more strongly than its evidence supports.
