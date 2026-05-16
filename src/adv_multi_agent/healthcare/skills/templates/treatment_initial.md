---
name: treatment_initial
description: Initial treatment-plan review; grounds every clinical claim in cited guidelines, checks drug-allergy/drug-organ/procedure contraindications, and stratifies patient-specific risk for attending physician verification
inputs:
  - patient_summary
  - proposed_plan
  - current_medications
  - lab_values
  - clinical_guidelines
  - contraindication_context
---
You are conducting a treatment-plan review for an attending physician to verify.
You have no stake in the outcome. Your job is to ground every clinical claim in
cited guidelines, check all contraindications, stratify patient-specific risk,
and ensure the plan is actionable for direct order entry.

BASE THE REVIEW ON THE INPUT DATA ONLY.

Patient summary: {patient_summary}
Proposed plan: {proposed_plan}
Current medications: {current_medications}
Lab values: {lab_values}
Clinical guidelines: {clinical_guidelines}
Contraindication context: {contraindication_context}

Produce a structured treatment-plan review with exactly these sections:

## Guideline review
For every clinical recommendation, cite the specific guideline document and
section number. Do not summarise; quote the operative language if short.
Flag any recommendation that lacks a guideline citation.

## Contraindication check
Check drug-allergy contraindications against patient_summary and
contraindication_context. Check drug-organ-failure contraindications
against lab_values (eGFR, liver enzymes, Child-Pugh if applicable).
Check procedure-comorbidity and procedure-medication contraindications.
Name the mechanism for each finding.

## Risk stratification
Stratify risk using patient-specific factors from patient_summary and
lab_values (age, comorbidities, organ function). Cite numeric thresholds.
Do not import baseline-population risk statistics not grounded in the data.

## Plan revisions
Provide specific dose/route/duration revisions. State exact orders.
If no revision is needed for an element, state "No change required."

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
