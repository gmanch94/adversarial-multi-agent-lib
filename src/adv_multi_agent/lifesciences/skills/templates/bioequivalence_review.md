---
name: bioequivalence_review
description: Reviewer criteria for a bioequivalence assessment; PK-BOUNDARY + STUDY-DESIGN + WAIVER-JUSTIFICATION flags with an out-of-limit-CI veto
inputs:
  - output
---

Evaluate this bioequivalence assessment on five dimensions. Score each 0–10.

1. PK-BOUNDARY CONFORMANCE (30%) — CRITICAL
   Does every pharmacokinetic parameter's 90% confidence interval fall within the
   applicable bioequivalence limits (typically 80.00-125.00%)? Penalise a CI
   outside the limits treated as equivalent. Flag under PK-BOUNDARY FLAGS:.

2. STUDY-DESIGN VALIDITY (25%) — CRITICAL
   Is the study design (condition, dosing, population, replicate design)
   appropriate to establish bioequivalence for this product? Penalise a design
   element inappropriate for the product. Flag under STUDY-DESIGN FLAGS:.

3. WAIVER / LIMIT JUSTIFICATION (20%) — CRITICAL
   Is every biowaiver or tightened/widened limit justified by the applicable
   criteria (BCS class, narrow-therapeutic-index, highly-variable drug)? Penalise
   an unjustified waiver or limit. Flag under WAIVER-JUSTIFICATION FLAGS:.

4. STATISTICAL RIGOR (15%)
   Are the intra-subject CV, replicate design, and outlier handling sound?
   Penalise weak statistical treatment.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which parameter, which design
   element, which criterion)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a bioequivalence conclusion is asserted while a PK parameter's 90%
confidence interval falls outside the applicable limits (or a required study /
tightened limit is absent). Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero PK-BOUNDARY FLAGS AND zero STUDY-DESIGN FLAGS AND zero
WAIVER-JUSTIFICATION FLAGS AND no VETO: ready for Clinical Pharmacology sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PK-BOUNDARY FLAGS: [bullet list, or "None detected"]
  STUDY-DESIGN FLAGS: [bullet list, or "None detected"]
  WAIVER-JUSTIFICATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
