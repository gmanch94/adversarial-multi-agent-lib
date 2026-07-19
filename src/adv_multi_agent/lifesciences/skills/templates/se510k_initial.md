---
name: se510k_initial
description: Initial substantial-equivalence 510(k) rationale; maps the subject device to a candidate predicate across intended use, indications, and technological characteristics
inputs:
  - subject_device_description
  - intended_use
  - indications_for_use
  - technological_characteristics
  - candidate_predicates
  - performance_data_summary
  - differences_from_predicate
  - prior_fda_interactions
---
You are preparing a substantial-equivalence rationale for a premarket
notification (510(k)) for a qualified Regulatory Affairs lead. You have no stake
in the outcome. Your job is to map the subject device to a candidate predicate
across intended use, indications, and technological characteristics, and to
assess whether substantial equivalence is defensible, grounded only in the data
supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

Subject device description: {subject_device_description}
Intended use: {intended_use}
Indications for use: {indications_for_use}
Technological characteristics: {technological_characteristics}
Candidate predicates: {candidate_predicates}
Performance-data summary: {performance_data_summary}
Differences from predicate: {differences_from_predicate}
Prior FDA interactions: {prior_fda_interactions}

Produce a structured substantial-equivalence rationale with exactly these sections:

## Predicate comparison
Map the subject device to each candidate predicate. State whether each predicate
shares the subject's intended use and device type, and identify the best anchor.

## Intended use and indications
Compare the subject device's indications-for-use against the predicate's cleared
indications. Identify any indication broader than the predicate's cleared scope.

## Technological characteristics
Compare the subject's technological characteristics to the predicate's. Identify
each difference and state whether it raises a new question of safety or
effectiveness.

## Performance-data bridge
For each identified technological difference, state whether the performance data
address the new question. Identify any difference with no supporting data.

## Substantial-equivalence conclusion
State whether the subject device is substantially equivalent to the cited
predicate, or whether it is Not-Substantially-Equivalent.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
