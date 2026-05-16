---
name: prior_auth_review
description: Reviewer criteria for prior authorization review; MEDICAL-NECESSITY + COVERAGE + DOCUMENTATION flags
inputs:
  - output
---
Evaluate the prior authorization review below on five dimensions (score each 0–10):

1. MEDICAL-NECESSITY GROUNDING (30%) — every necessity claim grounded in the
   submitted clinical guidelines (InterQual, MCG, specialty society); no
   paraphrasing from general practice?
2. COVERAGE-POLICY FIT (25%) — specific coverage policy section cited; outside
   policy flagged for medical-director review?
3. DOCUMENTATION SUFFICIENCY (20%) — missing documentation elements named
   specifically; no approval without required documents?
4. STEP-THERAPY VERIFICATION (15%) — alternatives_tried verified against payer
   step-therapy requirements with duration and outcome?
5. DECISION CLARITY (10%) — recommendation specific and actionable (approve /
   pend / deny / route to medical director)?

Flag deviations under: MEDICAL-NECESSITY FLAGS:, COVERAGE FLAGS:, DOCUMENTATION FLAGS:.

End your review with:
  Overall score: X/10
  Key issues: [bullet list]
  MEDICAL-NECESSITY FLAGS: [bullet list, or "None detected"]
  COVERAGE FLAGS: [bullet list, or "None detected"]
  DOCUMENTATION FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
