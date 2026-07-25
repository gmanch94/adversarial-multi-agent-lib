---
name: donor_revision
description: Revision prompt for a donor-eligibility determination review; addresses SCREENING-GAP, TESTING-GAP, and INELIGIBLE-RELEASE flags from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this donor-eligibility determination review. Address EVERY issue in the
reviewer's critique, especially any SCREENING-GAP FLAGS, TESTING-GAP FLAGS, or
INELIGIBLE-RELEASE FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Donor screening, Communicable-disease
testing, Eligibility determination, Plasma dilution and urgent-need documentation,
Eligibility conclusion, Claims).

For every SCREENING-GAP FLAG: complete the required screening element, or
acknowledge the donor cannot be determined eligible.

For every TESTING-GAP FLAG: cite the required communicable-disease test result
(right method, plasma dilution addressed), or acknowledge the gap.

For every INELIGIBLE-RELEASE FLAG: reconcile the eligible call with the evidence,
or acknowledge the donor is ineligible.
