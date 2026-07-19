---
name: promo_review
description: Reviewer criteria for promotional-material MLR review; five-dimension scoring with D-LIFESCI-3 veto criteria for material that would likely draw an FDA enforcement/untitled letter
inputs:
  - output
---
Evaluate this promotional-material review on five dimensions. Score each 0–10.

1. ON-LABEL CONSISTENCY (30%) — CRITICAL
   Is every claim within the approved indication, population, and dosing?
   Penalise any claim outside the approved label. Flag under OFF-LABEL FLAGS:.

2. FAIR BALANCE (25%) — CRITICAL
   Is risk / limitation information present and comparably prominent to the
   benefit claims? Penalise absent or de-emphasised risk information. Flag under
   FAIR-BALANCE FLAGS:.

3. CLAIM SUBSTANTIATION (20%) — CRITICAL
   Is each efficacy / comparative / superiority claim backed by substantial
   evidence or an adequate head-to-head citation? Penalise unsupported or
   inadequately cited claims. Flag under SUBSTANTIATION FLAGS:.

4. REFERENCE ADEQUACY (15%)
   Do the cited references actually support the claims they are attached to?
   Penalise references that do not support the claim.

5. ACTIONABILITY (10%)
   Is each finding specific enough for the MLR reviewer to resolve (which claim,
   which risk, which reference)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the material would likely draw an FDA enforcement or untitled
letter — clear off-label promotion, or omission of material risk information.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero OFF-LABEL FLAGS AND zero FAIR-BALANCE FLAGS AND zero
SUBSTANTIATION FLAGS AND no VETO: ready for MLR sign-off. Otherwise: requires
revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  OFF-LABEL FLAGS: [bullet list, or "None detected"]
  FAIR-BALANCE FLAGS: [bullet list, or "None detected"]
  SUBSTANTIATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
