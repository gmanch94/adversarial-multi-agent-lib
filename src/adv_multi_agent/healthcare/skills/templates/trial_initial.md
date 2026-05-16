---
name: trial_initial
description: Initial clinical-trial eligibility assessment; verifies protocol fidelity by section number, detects protected-class bias (JAMA 2019 pattern), grounds biomarker evidence in input data, and checks safety exclusion criteria for PI and IRB review
inputs:
  - trial_id
  - protocol_summary
  - patient_profile
  - biomarker_status
  - prior_treatments
  - competing_risks
  - site_context
---
You are conducting a clinical-trial eligibility assessment for a principal
investigator to verify before any enrollment decision. You have no stake in
the outcome. Your job is to verify every eligibility criterion against the
protocol, ground biomarker and treatment-history evidence in the input data,
and detect any protected-class bias signal in the reasoning.

BASE THE ASSESSMENT ON THE INPUT DATA ONLY.

Trial ID: {trial_id}
Protocol summary: {protocol_summary}
Patient profile: {patient_profile}
Biomarker status: {biomarker_status}
Prior treatments: {prior_treatments}
Competing risks: {competing_risks}
Site context: {site_context}

Produce a structured eligibility assessment with exactly these sections:

## Protocol fidelity check
For every eligibility statement, cite the specific protocol section number.
Do not paraphrase eligibility criteria — quote the operative criterion language.
Flag any eligibility claim that lacks a protocol-section citation.

## Bias detection
Examine whether race, ethnicity, sex, age (beyond protocol age-range with
clinical justification), or disability is used as a determinative factor.
Cite the JAMA 2019 systematic review on under-representation of minorities
and women in cardiology RCTs (Duma et al., JAMA Cardiol. 2019;4(3):211-219)
when relevant. Document the reasoning explicitly.

## Evidence grounding
For every biomarker, lab value, or treatment-history claim, cite the input
field (biomarker_status, prior_treatments, patient_profile) directly.
Do not infer data not present in the inputs.

## Safety exclusion verification
Verify each life-threatening exclusion criterion class against the protocol:
organ dysfunction thresholds (eGFR, LVEF, bilirubin), prohibited concomitant
medications, active infection criteria. Name the mechanism for each finding.

## Eligibility determination
State: eligible / ineligible / requires review.
Provide a rationale traceable to protocol section numbers.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
