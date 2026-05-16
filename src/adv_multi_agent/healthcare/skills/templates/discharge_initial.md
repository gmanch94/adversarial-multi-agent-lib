---
name: discharge_initial
description: Initial discharge plan risk assessment; anchors readmission risk and care gaps in patient-supplied data
inputs:
  - patient_summary
  - hospitalization_summary
  - proposed_discharge_plan
  - social_determinants
  - readmission_history
  - care_team_notes
---

You are assessing discharge readiness for a care coordinator to review.
Base every recommendation solely on the submitted patient data below.

Patient: {patient_summary}
Hospitalization: {hospitalization_summary}
Proposed plan: {proposed_discharge_plan}
Social determinants: {social_determinants}
Readmission history: {readmission_history}
Care team notes: {care_team_notes}

Produce a discharge plan assessment with:

## Readmission risk
Anchor risk in {readmission_history} and {hospitalization_summary}.
State LACE/HOSPITAL-equivalent rationale if high-risk.

## Care gaps
Name each missing service, referral, or follow-up appointment with timeframe.

## Social-determinant context
Address transportation, housing, food security, and insurance barriers
from {social_determinants} with concrete actions.

## Discharge plan revisions
Specific changes to {proposed_discharge_plan} with owner and timeline.

## Claims
Specific factual claims about the patient data that ground the plan.
