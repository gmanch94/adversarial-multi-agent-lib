---
name: diagnosis_review
description: Reviewer criteria for diagnosis-code audit; ACCURACY + COMPLIANCE + SPECIFICITY flags
inputs:
  - output
---

Evaluate the diagnosis-code audit below on five dimensions (score each 0–10):

1. CODE-TO-DOCUMENTATION ACCURACY (30%) — does every code map to specific documentation language?
2. GUIDELINE COMPLIANCE (25%) — alignment with ICD-10-CM Official Guidelines, AHA Coding Clinic, payer LCD.
3. SPECIFICITY (20%) — most specific code available used where documentation supports it?
4. PAYER-SPECIFIC FIT (15%) — DRG/APC alignment with payer policy.
5. ACTIONABILITY (10%) — recommendations specific enough for the coder to apply.

Flag deviations under: ACCURACY FLAGS:, COMPLIANCE FLAGS:, SPECIFICITY FLAGS:.

End your review with:
  Overall score: X/10
  Key issues: [bullet list]
  ACCURACY FLAGS: [bullet list, or "None detected"]
  COMPLIANCE FLAGS: [bullet list, or "None detected"]
  SPECIFICITY FLAGS: [bullet list, or "None detected"]

AUDIT:
{output}
