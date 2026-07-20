---
name: sterility_review
description: Reviewer criteria for a sterility assurance review; SAL + BIOBURDEN + VALIDATION-GAP flags with a sterile-release-without-demonstrated-SAL veto
inputs:
  - output
---

Evaluate this sterility assurance review on five dimensions. Score each 0–10.

1. SAL DEMONSTRATION (30%) — CRITICAL
   Is the claimed sterility assurance level demonstrated by the validation and
   routine-control data? Penalise a SAL claim not supported by the data. Flag
   under SAL FLAGS:.

2. BIOBURDEN CONTROL (25%) — CRITICAL
   Is routine bioburden within the validated limit, and is monitoring adequate to
   support the cycle? Penalise bioburden trending above the validated limit or
   inadequate monitoring. Flag under BIOBURDEN FLAGS:.

3. VALIDATION COMPLETENESS (20%) — CRITICAL
   Is every sterilization-validation element and sterile-barrier element present
   and current for the claimed SAL? Penalise a missing or expired validation
   element. Flag under VALIDATION-GAP FLAGS:.

4. ROUTINE-CONTROL / REVALIDATION RIGOR (15%)
   Are routine release controls (biological indicators, dosimetry) and the
   revalidation cadence adequate? Penalise weak routine control.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which control, which limit, which
   validation element)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if product is proposed for release as sterile while the claimed SAL
is not demonstrated (a validation gap, or bioburden above the validated limit).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SAL FLAGS AND zero BIOBURDEN FLAGS AND zero VALIDATION-GAP
FLAGS AND no VETO: ready for Microbiology Quality sign-off. Otherwise: requires
revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SAL FLAGS: [bullet list, or "None detected"]
  BIOBURDEN FLAGS: [bullet list, or "None detected"]
  VALIDATION-GAP FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
