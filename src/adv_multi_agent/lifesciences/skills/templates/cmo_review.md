---
name: cmo_review
description: Reviewer criteria for a CMO / CDMO qualification review; GMP-GAP + DATA-INTEGRITY + CAPACITY flags
inputs:
  - output
---

Evaluate this CMO / CDMO qualification review on five dimensions. Score each 0–10.

1. GMP COMPLIANCE (30%) — CRITICAL
   Are all GMP deficiencies from audits and inspection history remediated or
   under an adequate, time-bound CAPA? Penalise a GMP deficiency treated as
   closed without remediation. Flag under GMP-GAP FLAGS:.

2. DATA INTEGRITY (25%) — CRITICAL
   Is the CMO's data-integrity posture adequate (audit trails, review, no shared
   logins), with any weakness addressed? Penalise a data-integrity weakness left
   unaddressed. Flag under DATA-INTEGRITY FLAGS:.

3. CAPACITY & CONTINUITY (20%) — CRITICAL
   Is declared capacity (and business-continuity / redundancy) adequate for the
   committed volume and timeline? Penalise a capacity claim the assessment does
   not support. Flag under CAPACITY FLAGS:.

4. QUALITY-AGREEMENT COVERAGE (15%)
   Does an executed quality agreement define responsibilities, change control,
   and CAPA linkage? Penalise gaps in the quality-agreement coverage.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which observation, which system,
   which CAPA)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero GMP-GAP FLAGS AND zero DATA-INTEGRITY FLAGS AND zero
CAPACITY FLAGS: ready for Supplier Quality sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  GMP-GAP FLAGS: [bullet list, or "None detected"]
  DATA-INTEGRITY FLAGS: [bullet list, or "None detected"]
  CAPACITY FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
