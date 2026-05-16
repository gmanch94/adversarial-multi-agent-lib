---
name: drug_review
description: Reviewer criteria for drug-interaction review; SEVERITY FLAGS + EVIDENCE FLAGS + CONTRAINDICATION FLAGS + veto on absolute contraindication / QTc / NTI / cross-allergy
inputs:
  - output
---
Evaluate the drug-interaction review below on five dimensions. Score each 0–10.

1. SEVERITY ASSESSMENT (30%) — CRITICAL
   Is each flagged interaction graded against the formulary reference supplied
   in the case, not against training-data severity assumptions? Are severity
   ratings consistent with the cited monograph or guideline? Penalise severity
   claims not anchored to the supplied formulary_reference. Flag gaps under
   SEVERITY FLAGS:.

2. EVIDENCE-BASE CITATION (25%) — CRITICAL
   Does each interaction claim cite a specific monograph or guideline entry
   (e.g., "Lexicomp: warfarin + NSAID — major")? Penalise paraphrased severity
   without source. Flag gaps under EVIDENCE FLAGS:.

3. CONTRAINDICATION COMPLETENESS (20%) — CRITICAL
   Are drug-drug, drug-condition, AND drug-allergy contraindications checked?
   Is every drug in medication_list checked against new_medication? Flag every
   gap under CONTRAINDICATION FLAGS:.

4. ORGAN-FUNCTION DOSING (15%)
   For the patient's renal_function and hepatic_function values, are dose
   adjustments correctly calculated and grounded in the input values (not
   generic thresholds)? Penalise adjustments that ignore the supplied
   renal_function / hepatic_function data.

5. ACTIONABILITY (10%)
   Is the recommended action specific (hold, adjust dose, swap, monitor with
   specific parameter)? Vague recommendations ("use with caution") should be
   flagged.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Absolute contraindication between new_medication and any drug in
    medication_list per formulary or standard interaction reference.
  • QTc-prolonging combination in patient with documented cardiac history
    or prolonged baseline QTc.
  • Narrow-therapeutic-index interaction (warfarin + NSAID, lithium +
    thiazide, etc.) without a documented dose-adjustment plan.
  • Cross-allergy with a documented allergy in allergy_history.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
"Overall", "Key issues", or a "#" markdown header — the parser uses those
as stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SEVERITY FLAGS AND zero EVIDENCE FLAGS AND zero
CONTRAINDICATION FLAGS AND no VETO: review is ready for pharmacist sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SEVERITY FLAGS: [bullet list, or "None detected"]
  EVIDENCE FLAGS: [bullet list, or "None detected"]
  CONTRAINDICATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
