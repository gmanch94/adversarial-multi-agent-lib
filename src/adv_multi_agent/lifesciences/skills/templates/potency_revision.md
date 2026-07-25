---
name: potency_revision
description: Revision prompt for a CGT potency-assay adequacy review; addresses MOA-LINKAGE, LOT-RELEASE-CLAIM, and ASSAY-VALIDATION flags from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this potency-assay adequacy review. Address EVERY issue in the reviewer's
critique, especially any MOA-LINKAGE FLAGS, LOT-RELEASE-CLAIM FLAGS, or
ASSAY-VALIDATION FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Mechanism-of-action linkage, Lot-release
claim, Assay validation, Surrogate / matrix justification, Release-adequacy
conclusion, Claims).

For every MOA-LINKAGE FLAG: link the readout to the mechanism of action, or
acknowledge the assay does not measure clinical activity.

For every LOT-RELEASE-CLAIM FLAG: narrow the release claim to what the assay and
criteria support.

For every ASSAY-VALIDATION FLAG: cite the validation element that resolves the
gap, or acknowledge the method is not validated for release.
