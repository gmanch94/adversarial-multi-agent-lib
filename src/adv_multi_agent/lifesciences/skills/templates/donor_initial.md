---
name: donor_initial
description: Initial donor-eligibility determination review (21 CFR 1271 Subpart C); assesses risk-factor screening, communicable-disease testing, and the eligibility call against the supplied data
inputs:
  - donation_type
  - donor_screening_summary
  - donor_testing_summary
  - agents_considered
  - plasma_dilution_assessment
  - physical_assessment_or_records_review
  - retesting_or_repeat_status
  - urgent_medical_need_flag
---
You are reviewing a 21 CFR 1271 Subpart C donor-eligibility determination for an
allogeneic cell or tissue product for a qualified Quality Assurance / Tissue-safety
officer. You have no stake in the outcome. Assess whether the screening and
communicable-disease testing support an eligible determination, grounded only in
the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

Donation type: {donation_type}
Donor screening summary: {donor_screening_summary}
Donor testing summary: {donor_testing_summary}
Agents considered: {agents_considered}
Plasma-dilution assessment: {plasma_dilution_assessment}
Physical assessment / records review: {physical_assessment_or_records_review}
Retesting / repeat status: {retesting_or_repeat_status}
Urgent-medical-need flag: {urgent_medical_need_flag}

Produce a structured review with exactly these sections:

## Donor screening
State whether the risk-factor screening (history, physical, records) is complete
and correctly interpreted; identify any gap.

## Communicable-disease testing
State whether the required testing is present, by the right method, and correctly
read (with plasma dilution addressed); identify any gap.

## Eligibility determination
State whether the "eligible" call is consistent with the screening and testing;
identify any unsupported eligible call.

## Plasma dilution and urgent-need documentation
State whether plasma dilution and any urgent-medical-need path are assessed and
documented.

## Eligibility conclusion
State whether the donor is eligible on the supplied evidence, or whether the
determination is unsupported.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
