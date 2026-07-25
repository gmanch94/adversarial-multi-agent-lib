---
name: rmat_revision
description: Revision prompt for an RMAT designation eligibility assessment; addresses EVIDENCE-STRETCH, SERIOUS-CONDITION, and UNMET-NEED flags from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this RMAT designation eligibility assessment based on reviewer critique.
Address EVERY issue, especially any EVIDENCE-STRETCH FLAGS, SERIOUS-CONDITION
FLAGS, or UNMET-NEED FLAGS.

ORIGINAL ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Regenerative-medicine-therapy
qualification, Serious or life-threatening condition, Preliminary clinical
evidence, Unmet medical need, Eligibility conclusion, Claims).

For every EVIDENCE-STRETCH FLAG: cite the underpowered / uncontrolled /
wrong-endpoint study and re-characterise it; do not assert potential the evidence
does not support.

For every SERIOUS-CONDITION FLAG: re-characterise the condition seriousness to
match the supplied data.

For every UNMET-NEED FLAG: reconcile the unmet-need claim against the available
therapy; do not overstate the gap.
