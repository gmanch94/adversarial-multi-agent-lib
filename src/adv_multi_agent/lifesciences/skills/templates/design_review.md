---
name: design_review
description: Reviewer criteria for a design-control traceability audit; TRACE-GAP + VERIFICATION + VALIDATION flags
inputs:
  - output
---

Evaluate this design-control traceability audit on five dimensions. Score each 0–10.

1. INPUT-OUTPUT TRACEABILITY (30%) — CRITICAL
   Does every design input (requirement) trace to at least one design output
   (specification), and every output trace back to an input? Penalise orphan
   inputs and orphan outputs. Flag each broken link under TRACE-GAP FLAGS:.

2. VERIFICATION EVIDENCE (25%) — CRITICAL
   Does every design output have verification evidence demonstrating the output
   meets the input? Penalise outputs asserted verified without cited evidence.
   Flag gaps under VERIFICATION FLAGS:.

3. VALIDATION EVIDENCE (20%) — CRITICAL
   Does every user need have design-validation evidence (device meets user
   needs / intended use)? Penalise V&V conflation (verification cited where
   validation is required). Flag gaps under VALIDATION FLAGS:.

4. RISK-CONTROL LINKAGE (15%)
   Are ISO 14971 risk controls traced to the verification/validation that
   confirms their effectiveness? Penalise risk controls with no confirming V&V.

5. ACTIONABILITY (10%)
   Is each gap specific enough for a QE to close (which input, which output,
   what evidence is missing)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero TRACE-GAP FLAGS AND zero VERIFICATION FLAGS AND zero
VALIDATION FLAGS: ready for Design Assurance sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  TRACE-GAP FLAGS: [bullet list, or "None detected"]
  VERIFICATION FLAGS: [bullet list, or "None detected"]
  VALIDATION FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
