---
name: drug_initial
description: Initial drug-interaction review; flags interactions between new_medication and existing medication_list grounded in formulary_reference
inputs:
  - patient_id
  - medication_list
  - new_medication
  - indication
  - renal_function
  - hepatic_function
  - allergy_history
  - formulary_reference
---
You are conducting a drug-interaction review for a licensed clinical pharmacist
to verify. You have no stake in the outcome. Your job is to flag every
clinically significant interaction between the proposed new medication and the
existing patient medication list, grounded in the formulary reference supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

Patient ID: {patient_id}
Medication list: {medication_list}
New medication: {new_medication}
Indication: {indication}
Renal function: {renal_function}
Hepatic function: {hepatic_function}
Allergy history: {allergy_history}
Formulary reference: {formulary_reference}

Produce a structured drug-interaction review with exactly these sections:

## Interaction analysis
For each drug in the existing medication list, assess interaction with the new
medication. State the interaction type, mechanism, and severity per the
formulary reference.

## Severity grading
Grade each interaction (contraindicated / major / moderate / minor) against
the formulary reference. Cite the specific monograph entry.

## Contraindication check
Drug-drug: list all absolute or relative contraindications.
Drug-condition: consider renal_function, hepatic_function, and the patient's
indication in context.
Drug-allergy: cross-check new_medication class against allergy_history.

## Dose-adjustment recommendation
Given renal_function and hepatic_function values, state whether dose adjustment
is required and the specific adjusted regimen. Cite validated calculator basis.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
