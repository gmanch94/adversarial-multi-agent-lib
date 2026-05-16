---
name: discharge_review
description: Reviewer criteria for discharge plan risk assessment; READMISSION + CARE-GAP + SOCIAL-DETERMINANT flags
inputs:
  - output
---

Evaluate the discharge plan assessment below on five dimensions (score each 0–10):

1. READMISSION-RISK ASSESSMENT (30%) — risk grounded in readmission_history and
   hospitalization_summary; LACE/HOSPITAL-equivalent rationale for high-risk patients?
2. CARE-GAP IDENTIFICATION (25%) — specific missing services, referrals, and
   follow-up appointments named with timeframes?
3. SOCIAL-DETERMINANT ATTENTION (20%) — transportation, housing, food security,
   and insurance barriers addressed with concrete actions?
4. PLAN ACTIONABILITY (15%) — specific destination, appointment windows, and
   medication reconciliation stated?
5. CARE-TEAM ALIGNMENT (10%) — plan coherent with nursing, PT, OT, and SW notes?

Flag deviations under: READMISSION FLAGS:, CARE-GAP FLAGS:, SOCIAL-DETERMINANT FLAGS:.

End your review with:
  Overall score: X/10
  Key issues: [bullet list]
  READMISSION FLAGS: [bullet list, or "None detected"]
  CARE-GAP FLAGS: [bullet list, or "None detected"]
  SOCIAL-DETERMINANT FLAGS: [bullet list, or "None detected"]

ASSESSMENT:
{output}
