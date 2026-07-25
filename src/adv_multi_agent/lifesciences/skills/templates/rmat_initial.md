---
name: rmat_initial
description: Initial RMAT designation eligibility assessment; assesses the regenerative-medicine-therapy, serious-condition, and preliminary-clinical-evidence prongs against the supplied data
inputs:
  - product_description
  - serious_condition_rationale
  - preliminary_clinical_evidence
  - unmet_medical_need
  - intent_to_address_unmet_need
  - available_therapy_landscape
  - prior_fda_interactions
---
You are assessing eligibility for Regenerative Medicine Advanced Therapy (RMAT)
designation for a Regulatory Strategy lead to review. You have no stake in the
outcome. Assess the three statutory prongs — regenerative-medicine therapy,
serious or life-threatening condition, and preliminary clinical evidence
indicating potential to address an unmet need — against the supplied data only.

BASE EVERY FINDING ON THE INPUT DATA ONLY. Do not assert an eligibility
conclusion not grounded in the evidence below.

Product description: {product_description}
Serious-condition rationale: {serious_condition_rationale}
Preliminary clinical evidence: {preliminary_clinical_evidence}
Unmet medical need: {unmet_medical_need}
Intent to address unmet need: {intent_to_address_unmet_need}
Available therapy landscape: {available_therapy_landscape}
Prior FDA interactions: {prior_fda_interactions}

Produce an assessment with:

## Regenerative-medicine-therapy qualification
State whether the product qualifies as a regenerative-medicine therapy.

## Serious or life-threatening condition
State whether the condition meets the serious-or-life-threatening bar.

## Preliminary clinical evidence
Assess whether the preliminary clinical evidence credibly indicates potential to
address the condition; name any evidence gap.

## Unmet medical need
Assess the unmet-need claim against the available-therapy landscape.

## Eligibility conclusion
State whether the product appears eligible for RMAT designation, or the gaps that
prevent it.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
