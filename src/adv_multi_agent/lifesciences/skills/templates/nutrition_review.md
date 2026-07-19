---
name: nutrition_review
description: Reviewer criteria for a nutrition label-claim review; CLAIM-SUBSTANTIATION + NUTRIENT-ADEQUACY + ALLERGEN flags
inputs:
  - output
---

Evaluate this nutrition label-claim review on five dimensions. Score each 0–10.

1. CLAIM SUBSTANTIATION (30%) — CRITICAL
   Does every structure-function claim have competent-reliable scientific
   evidence in the substantiation dossier, and every disease (health) claim an
   authorization? Penalise a disease claim made as a structure-function claim
   without authorization. Flag gaps under CLAIM-SUBSTANTIATION FLAGS:.

2. NUTRIENT ADEQUACY (25%) — CRITICAL
   Is the nutrient profile adequate against the applicable requirement for the
   product category and target population (e.g. infant-formula nutrient
   minimums, 21 CFR 107)? Penalise a profile below a required minimum. Flag
   gaps under NUTRIENT-ADEQUACY FLAGS:.

3. ALLERGEN DECLARATION (20%) — CRITICAL
   Is every major allergen declared, and is a cross-contact statement present
   where the process warrants it? Penalise an undeclared major allergen. Flag
   gaps under ALLERGEN FLAGS:.

4. CLAIM-CATEGORY ROUTING (15%)
   Is each claim correctly categorised (structure-function vs nutrient-content
   vs health) and does the label meet that category's requirements? Penalise
   mis-categorised claims.

5. ACTIONABILITY (10%)
   Is each finding specific enough for a regulatory reviewer to resolve (which
   claim, which nutrient, which allergen)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero CLAIM-SUBSTANTIATION FLAGS AND zero NUTRIENT-ADEQUACY
FLAGS AND zero ALLERGEN FLAGS: ready for Nutrition Regulatory sign-off.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  CLAIM-SUBSTANTIATION FLAGS: [bullet list, or "None detected"]
  NUTRIENT-ADEQUACY FLAGS: [bullet list, or "None detected"]
  ALLERGEN FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
