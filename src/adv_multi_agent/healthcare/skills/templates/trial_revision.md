---
name: trial_revision
description: Revision prompt for clinical-trial eligibility assessment; addresses BIAS FLAGS (protected-class attribute justification), ELIGIBILITY FLAGS (protocol-section citations), and EVIDENCE FLAGS (input-grounded biomarker citations)
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this clinical-trial eligibility assessment. Address EVERY issue in
the reviewer's critique, especially any BIAS FLAGS, ELIGIBILITY FLAGS, or
EVIDENCE FLAGS.

PREVIOUS ASSESSMENT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Protocol fidelity check, Bias
detection, Evidence grounding, Safety exclusion verification, Eligibility
determination, Claims).

⚠️  For any BIAS FLAG: document protocol-specified clinical justification for
any use of a protected-class attribute; if none exists, remove it from the
determinative reasoning and flag for IRB review.
⚠️  For any ELIGIBILITY FLAG: cite the protocol section number; do not
paraphrase eligibility criteria.
⚠️  For any EVIDENCE FLAG: cite the biomarker / lab / treatment-history input
directly; do not infer data not present in the inputs.
