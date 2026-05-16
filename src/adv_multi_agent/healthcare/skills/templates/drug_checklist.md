---
name: drug_checklist
description: Clinical pharmacist sign-off checklist for drug-interaction review; includes veto-escalation row when vetoed
inputs:
  - veto_reason
  - severity_flags
  - evidence_flags
  - contraindication_flags
  - new_medication
  - renal_function
  - hepatic_function
---
[OWNER: Clinical Pharmacist]

{%- if veto_reason %}
[ ] REVIEWER VETO — escalate to clinical pharmacist BEFORE any prescribing action
    Veto directive: {veto_reason}
{%- endif %}

{%- if severity_flags %}
[ ] Resolve SEVERITY FLAGS — re-grade against live Lexicomp / Micromedex monograph,
    not training-data severity assumptions
{%- endif %}

{%- if evidence_flags %}
[ ] Resolve EVIDENCE FLAGS — cite specific monograph or guideline entry for each
    flagged interaction; do not paraphrase severity
{%- endif %}

{%- if contraindication_flags %}
[ ] Resolve CONTRAINDICATION FLAGS — confirm each drug-drug, drug-condition, and
    drug-allergy pair; name the contraindicating mechanism explicitly
{%- endif %}

[ ] Verify every flagged interaction against live Lexicomp / Micromedex monograph
    for: {new_medication}

[ ] Confirm renal / hepatic dose adjustments against validated calculator
    (Cockcroft-Gault for renal: {renal_function}; Child-Pugh for hepatic: {hepatic_function})

[ ] Pharmacist sign-off in EHR before dispensing
