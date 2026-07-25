---
name: donor_review
description: Reviewer criteria for a donor-eligibility determination review (1271 Subpart C); five-dimension scoring with D-LIFESCI-8 veto for an ineligible / inadequately screened-tested donor
inputs:
  - output
---
Evaluate this donor-eligibility determination review on five dimensions. Score each 0–10.

1. DONOR SCREENING (30%) — CRITICAL
   Is the required risk-factor screening (history, physical assessment, records
   review) complete and correctly interpreted? Penalise incomplete or misread
   screening. Flag under SCREENING-GAP FLAGS:.

2. COMMUNICABLE-DISEASE TESTING (25%) — CRITICAL
   Is the required communicable-disease testing present, by the right method, and
   correctly read (with plasma-dilution addressed)? Penalise missing / wrong /
   misread testing. Flag under TESTING-GAP FLAGS:.

3. ELIGIBILITY DETERMINATION (20%) — CRITICAL
   Is the "eligible" call consistent with the screening and testing evidence, and
   is any urgent-medical-need path documented as such rather than as routine
   eligibility? Penalise an eligible call the evidence does not support. Flag
   under INELIGIBLE-RELEASE FLAGS:.

4. PLASMA-DILUTION & URGENT-NEED DOCUMENTATION (15%)
   Are plasma dilution and any urgent-medical-need path assessed and documented?
   Penalise unaddressed dilution or undocumented urgent-need use.

5. ACTIONABILITY (10%)
   Is each finding specific enough for QA to resolve (which screen, which test,
   which agent)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if releasing the allogeneic product would use an ineligible or
inadequately screened / tested donor — a communicable-disease transmission risk.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SCREENING-GAP FLAGS AND zero TESTING-GAP FLAGS AND zero
INELIGIBLE-RELEASE FLAGS AND no VETO: ready for QA / Tissue-safety sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SCREENING-GAP FLAGS: [bullet list, or "None detected"]
  TESTING-GAP FLAGS: [bullet list, or "None detected"]
  INELIGIBLE-RELEASE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
