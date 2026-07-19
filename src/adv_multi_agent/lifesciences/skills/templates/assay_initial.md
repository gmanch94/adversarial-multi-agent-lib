---
name: assay_initial
description: Initial IVD assay performance-claim review; maps each sensitivity/specificity/interference claim to the underlying study data and its confidence interval
inputs:
  - assay_description
  - intended_use
  - analyte_measurand
  - claim_set
  - study_design_summary
  - interference_panel_tested
  - cross_reactivity_data
  - stability_claims
---
You are conducting an assay performance-claim review for a qualified Diagnostics
Regulatory / R&D reviewer. You have no stake in the outcome. Your job is to map
each proposed performance claim to the underlying study data, assess whether the
claim stays within the study confidence interval and tested matrices, and
recommend a defensible claim set, grounded only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

Assay description: {assay_description}
Intended use: {intended_use}
Analyte / measurand: {analyte_measurand}
Claim set: {claim_set}
Study design summary: {study_design_summary}
Interference panel tested: {interference_panel_tested}
Cross-reactivity data: {cross_reactivity_data}
Stability claims: {stability_claims}

Produce a structured assay performance-claim review with exactly these sections:

## Claim-by-claim data mapping
Map each proposed claim to the specific study, n, and confidence interval that
supports it. State the source study for each claim.

## Sensitivity assessment
For each sensitivity claim, compare the point estimate against the study n and
lower CI bound. State whether the claim is supported or overstated.

## Specificity assessment
For each specificity / false-positive-rate claim, compare against the data and
its CI. State whether the claim is supported or overstated.

## Interference and cross-reactivity
For each claimed matrix and population, state whether interferents and
cross-reactants were tested. Identify any claimed matrix with untested
interferents.

## Recommended claim set
State the defensible claim set: each performance claim re-stated within the
study CI and restricted to the tested matrix/population.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
