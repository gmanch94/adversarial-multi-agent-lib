---
name: treatment_review
description: Reviewer criteria for treatment-plan review; five-dimension scoring with D-HEALTH-4 veto criteria for absolute drug-allergy, drug-organ-failure, and procedure-condition contraindications
inputs:
  - output
---
Evaluate this treatment-plan review on five dimensions. Score each 0–10.

1. GUIDELINE GROUNDING (30%) — CRITICAL
   Is every clinical claim grounded in a cited guideline? Citations must name
   the guideline document and section, not just summarise conclusions.
   Penalise claims not anchored to a named guideline with a section reference.
   Flag gaps under GUIDELINE FLAGS:.

2. CONTRAINDICATION COMPLETENESS (25%) — CRITICAL
   Are drug-allergy, drug-organ-failure, and procedure-condition
   contraindications fully checked? Is each contraindication mechanism named
   (not just asserted)? Penalise reviews that assert "no contraindications"
   without checking allergy history, organ function (eGFR, liver function),
   and procedure-comorbidity pairs.
   Flag gaps under CONTRAINDICATION FLAGS:.

3. RISK STRATIFICATION (20%) — CRITICAL
   Is risk stratified against patient-specific factors (age, comorbidity, lab
   values) rather than baseline-population risk? Is the numeric basis cited
   (e.g. eGFR value, Child-Pugh score)?
   Flag gaps under RISK FLAGS:.

4. DOSE/ROUTE/DURATION SPECIFICITY (15%)
   Are exact doses, routes, and durations specified? Vague recommendations
   ("start a statin") must be flagged as insufficient for order entry.

5. ACTIONABILITY (10%)
   Can the attending physician execute or reject this plan directly? Vague
   recommendations ("consider cardiology consult") that lack a decision
   criterion must be flagged.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Absolute drug-allergy contraindication present in patient_summary or
    contraindication_context (e.g. documented anaphylaxis to penicillin,
    proposed plan includes penicillin-class antibiotic).
  • Drug-organ-failure contraindication (e.g. renally-cleared drug at full
    dose with eGFR below the guideline threshold; hepatotoxic drug in
    Child-Pugh C cirrhosis).
  • Procedure in proposed_plan is contraindicated given documented
    comorbidity or medication (e.g. contrast-enhanced procedure in CKD3
    without prophylaxis; elective surgery on anticoagulated patient
    without bridging plan).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those
  as stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score ≥ 8.0 AND zero GUIDELINE FLAGS AND zero CONTRAINDICATION FLAGS AND zero
RISK FLAGS AND no VETO: plan is ready for attending physician sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  GUIDELINE FLAGS: [bullet list, or "None detected"]
  CONTRAINDICATION FLAGS: [bullet list, or "None detected"]
  RISK FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
