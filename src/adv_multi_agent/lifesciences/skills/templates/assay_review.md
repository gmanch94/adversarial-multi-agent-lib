---
name: assay_review
description: Reviewer criteria for IVD assay performance-claim review; five-dimension scoring with D-LIFESCI-2 veto criteria for claims the study data cannot support
inputs:
  - output
---
Evaluate this assay performance-claim review on five dimensions. Score each 0–10.

1. SENSITIVITY-CLAIM SUPPORT (30%) — CRITICAL
   Does each clinical/analytical sensitivity claim stay within what the study n
   and its confidence interval support? Penalise a point-estimate claim that
   ignores the lower CI bound or an underpowered n. Flag under
   SENSITIVITY-CLAIM FLAGS:.

2. SPECIFICITY-CLAIM SUPPORT (25%) — CRITICAL
   Is the specificity / false-positive-rate claim supported by the data and its
   CI? Penalise an overstated specificity claim. Flag under SPECIFICITY-CLAIM FLAGS:.

3. INTERFERENCE / CROSS-REACTIVITY (20%) — CRITICAL
   Are interferents and cross-reactants tested for every claimed matrix and
   population? Penalise a claimed matrix with untested interferents. Flag under
   INTERFERENCE FLAGS:.

4. STUDY-DESIGN ADEQUACY (15%)
   Is the study design adequate (CLSI EP protocol, appropriate reference method,
   representative population) to support the claim set? Penalise design gaps.

5. ACTIONABILITY (10%)
   Is each finding specific enough for R&D to resolve (which claim, which study,
   which interferent)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a performance claim is overstated enough that releasing it would
create a misdiagnosis risk or an adulteration/misbranding exposure (a claim the
data cannot support in the claimed intended-use population).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SENSITIVITY-CLAIM FLAGS AND zero SPECIFICITY-CLAIM FLAGS
AND zero INTERFERENCE FLAGS AND no VETO: ready for Diagnostics Regulatory
sign-off. Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SENSITIVITY-CLAIM FLAGS: [bullet list, or "None detected"]
  SPECIFICITY-CLAIM FLAGS: [bullet list, or "None detected"]
  INTERFERENCE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
