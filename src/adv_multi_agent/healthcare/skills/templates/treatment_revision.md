---
name: treatment_revision
description: Revision prompt for treatment-plan review; addresses GUIDELINE FLAGS, CONTRAINDICATION FLAGS, and RISK FLAGS raised by the reviewer
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this treatment-plan review. Address EVERY issue in the reviewer's
critique, especially any GUIDELINE FLAGS, CONTRAINDICATION FLAGS, or RISK FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Guideline review, Contraindication
check, Risk stratification, Plan revisions, Claims).

⚠️  For any GUIDELINE FLAG: cite the guideline document and section, not a summary.
⚠️  For any CONTRAINDICATION FLAG: name the specific contraindication mechanism
(drug-allergy, drug-organ, drug-condition).
⚠️  For any RISK FLAG: stratify risk against patient-specific factors
(age, comorbidity, lab values); do not import baseline-population risk.
