---
name: rmat_review
description: Reviewer criteria for an RMAT designation eligibility assessment; five-dimension scoring flagging EVIDENCE-STRETCH, SERIOUS-CONDITION, and UNMET-NEED overstatements (no veto)
inputs:
  - output
---
Evaluate this RMAT designation eligibility assessment on five dimensions. Score each 0–10.

1. PRELIMINARY CLINICAL EVIDENCE (30%) — CRITICAL
   Does the preliminary clinical evidence (n, design, endpoint, effect size)
   credibly indicate the therapy has the potential to address the condition?
   Penalise evidence that is underpowered, uncontrolled, or wrong-endpoint yet
   argued as sufficient. Flag under EVIDENCE-STRETCH FLAGS:.

2. SERIOUS OR LIFE-THREATENING CONDITION (25%) — CRITICAL
   Does the condition meet the serious-or-life-threatening bar as characterised?
   Penalise an overstated seriousness. Flag under SERIOUS-CONDITION FLAGS:.

3. UNMET MEDICAL NEED (20%) — CRITICAL
   Is the unmet-need claim supported against the available-therapy landscape?
   Penalise an overstated unmet need where adequate therapy exists. Flag under
   UNMET-NEED FLAGS:.

4. REGENERATIVE-MEDICINE-THERAPY QUALIFICATION (15%)
   Does the product qualify as a regenerative-medicine therapy (cell therapy,
   therapeutic tissue-engineering, human cell/tissue product, or combination)?
   Penalise a product that does not qualify.

5. ACTIONABILITY (10%)
   Is each finding specific enough for Regulatory Strategy to resolve (which
   study, which endpoint, which comparator)? Penalise vague findings.

Overall score = weighted average.
Score >= 7.5 AND zero EVIDENCE-STRETCH FLAGS AND zero SERIOUS-CONDITION FLAGS AND
zero UNMET-NEED FLAGS: ready for Regulatory Strategy sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  EVIDENCE-STRETCH FLAGS: [bullet list, or "None detected"]
  SERIOUS-CONDITION FLAGS: [bullet list, or "None detected"]
  UNMET-NEED FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
