---
name: diagnosis_initial
description: Initial draft of a diagnosis-code audit; maps each proposed code to encounter documentation
inputs:
  - encounter_summary
  - proposed_codes
  - provider_specialty
  - payer_guidelines
  - clinical_context
---

You are auditing diagnosis and procedure codes for a credentialed coder.

For each proposed code in {proposed_codes}:
1. Cite the specific language in {encounter_summary} that supports the code.
2. Note any ICD-10-CM Official Guideline / AHA Coding Clinic / {payer_guidelines} reference that applies.
3. Identify whether a more specific code is available for this clinical context.

Output sections: ## Code accuracy, ## Compliance check, ## Specificity gaps, ## Recommended changes, ## Claims.

Specialty context: {provider_specialty}. Clinical context: {clinical_context}.
