---
name: csv_review
description: Reviewer criteria for a computer system validation review; INTENDED-USE + TRACE-GAP + TEST-EVIDENCE flags
inputs:
  - output
---

Evaluate this computer system validation review on five dimensions. Score each 0–10.

1. INTENDED-USE & RISK FIT (30%) — CRITICAL
   Is the validation scope matched to the stated GxP intended use and GAMP 5
   category (effort proportionate to risk and configuration/customization)?
   Penalise scope that under- or over-shoots the intended use. Flag mismatches
   under INTENDED-USE FLAGS:.

2. REQUIREMENT-TEST TRACEABILITY (25%) — CRITICAL
   Does every requirement (URS/FS) trace to at least one executed test, and
   every test back to a requirement? Penalise orphan requirements and orphan
   tests. Flag each broken link under TRACE-GAP FLAGS:.

3. TEST EVIDENCE (20%) — CRITICAL
   Does every requirement asserted verified have cited IQ/OQ/PQ execution
   evidence? Penalise requirements marked verified without cited, approved
   evidence. Flag gaps under TEST-EVIDENCE FLAGS:.

4. RISK-BASED VALIDATION RIGOR (15%)
   Is the depth of testing proportionate to the GAMP 5 category and patient/
   product risk (Category 3 vs 4 vs 5 effort)? Penalise a rigor level that does
   not follow from the risk assessment.

5. ACTIONABILITY (10%)
   Is each finding specific enough for the CSV team to close (which requirement,
   which test, what evidence is missing)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero INTENDED-USE FLAGS AND zero TRACE-GAP FLAGS AND zero
TEST-EVIDENCE FLAGS: ready for CSV / Quality IT sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  INTENDED-USE FLAGS: [bullet list, or "None detected"]
  TRACE-GAP FLAGS: [bullet list, or "None detected"]
  TEST-EVIDENCE FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
