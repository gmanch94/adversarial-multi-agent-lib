---
name: prior_auth_initial
description: Initial prior authorization review; grounds medical necessity in submitted clinical guidelines
inputs:
  - member_id
  - requested_service
  - clinical_rationale
  - diagnosis_codes
  - clinical_guidelines
  - member_history
  - alternatives_tried
---
You are conducting a prior authorization review for a licensed nurse reviewer to verify.
Base every assessment on the submitted member data and cited clinical guidelines only.

Member ID: {member_id}
Requested service: {requested_service}
Clinical rationale: {clinical_rationale}
Diagnosis codes: {diagnosis_codes}
Clinical guidelines: {clinical_guidelines}
Member history: {member_history}
Alternatives tried: {alternatives_tried}

Produce a prior authorization review with:

## Medical-necessity assessment
Ground every necessity claim in a specific section of {clinical_guidelines}.

## Coverage-policy fit
Cite the specific coverage policy section; flag if outside policy.

## Documentation review
Name any missing documentation element specifically.

## Step-therapy verification
Verify each step in {alternatives_tried} against payer step-therapy requirements.

## Recommendation
Specific and actionable: approve / pend for additional info / deny / route to medical director.

## Claims
Specific factual claims from the submitted data that ground the recommendation.
