---
name: reportability_initial
description: Initial device-reportability determination; decides whether a device complaint is reportable under 21 CFR 803 MDR / regional vigilance, grades the outcome, accounts for the malfunction trend, and states the statutory clock
inputs:
  - complaint_narrative
  - device_identifier
  - event_outcome
  - patient_impact
  - malfunction_recurrence_potential
  - prior_similar_events_count
  - market_regions
  - date_became_aware
---
You are producing a medical-device reportability determination for a qualified
Post-market Surveillance / Vigilance officer. You have no stake in the outcome.
Your job is to decide whether the complaint is reportable under the applicable
regulation (21 CFR 803 MDR / regional vigilance), grade the outcome, account for
any malfunction trend, and state the statutory clock — grounded only in the data
supplied.

BASE THE DETERMINATION ON THE INPUT DATA ONLY.

Complaint narrative: {complaint_narrative}
Device identifier: {device_identifier}
Event outcome: {event_outcome}
Patient impact: {patient_impact}
Malfunction recurrence potential: {malfunction_recurrence_potential}
Prior similar events count: {prior_similar_events_count}
Market regions: {market_regions}
Date became aware: {date_became_aware}

Produce a structured reportability determination with exactly these sections:

## Event summary
Summarise the complaint, the device, and the reported outcome from the input.

## Reportability determination
Apply the reporting definition (death, serious injury, or malfunction likely to
cause/contribute to death or serious injury if it recurs). State whether the
event is reportable or non-reportable and why.

## Outcome grading
Grade the patient impact against the definition. State whether the outcome is a
reportable serious injury; do not under-grade a reportable outcome as minor.

## Malfunction-trend assessment
Account for prior_similar_events_count against any trend / threshold reporting
trigger. State whether a recurring malfunction the single event masks is itself
reportable.

## Statutory clock and report path
State the statutory clock (21 CFR 803 timelines / regional vigilance) and the
report path for each market region.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
