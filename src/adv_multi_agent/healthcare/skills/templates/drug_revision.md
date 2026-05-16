---
name: drug_revision
description: Revision prompt for drug-interaction review; addresses SEVERITY FLAGS, EVIDENCE FLAGS, CONTRAINDICATION FLAGS from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this drug-interaction review. Address EVERY issue in the reviewer's
critique, especially any SEVERITY FLAGS, EVIDENCE FLAGS, or
CONTRAINDICATION FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Interaction analysis, Severity
grading, Contraindication check, Dose-adjustment recommendation, Claims).

For every SEVERITY FLAG: re-grade against the supplied formulary reference;
do not import training-data severity assumptions.

For every EVIDENCE FLAG: cite the specific monograph or guideline entry
(e.g., "Lexicomp: warfarin + NSAID — major"); do not paraphrase severity.

For every CONTRAINDICATION FLAG: name the contraindicating drug pair or
allergy mechanism explicitly; do not omit drug-condition or drug-allergy
interactions.
