---
name: gxp_review
description: Reviewer criteria for a GxP data-integrity assessment; ALCOA + AUDIT-TRAIL + ATTRIBUTION flags
inputs:
  - output
---

Evaluate this GxP data-integrity assessment on five dimensions. Score each 0–10.

1. ALCOA+ COMPLIANCE (30%) — CRITICAL
   Is every ALCOA+ attribute (attributable, legible, contemporaneous, original,
   accurate — plus complete, consistent, enduring, available) demonstrably met
   for the records described? Penalise any attribute asserted met without
   evidence. Flag each unmet attribute under ALCOA FLAGS:.

2. AUDIT-TRAIL ADEQUACY (25%) — CRITICAL
   Is the audit trail enabled, tamper-evident, and actually reviewed (not merely
   available)? Penalise audit trails that are disabled, editable, or never
   reviewed. Flag gaps under AUDIT-TRAIL FLAGS:.

3. ATTRIBUTION & ACCESS CONTROL (20%) — CRITICAL
   Is every action uniquely attributable to a person and a time, with adequate
   segregation of duties and no shared logins or back-dating? Penalise
   attribution failures. Flag gaps under ATTRIBUTION FLAGS:.

4. DATA-LIFECYCLE COVERAGE (15%)
   Does the assessment cover the full data lifecycle (create → process → review
   → report → retain → retrieve → archive)? Penalise a lifecycle stage left
   unassessed.

5. ACTIONABILITY (10%)
   Is each finding specific enough for QA to remediate (which record, which
   attribute, what evidence is missing)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero ALCOA FLAGS AND zero AUDIT-TRAIL FLAGS AND zero
ATTRIBUTION FLAGS: ready for QA / Data Integrity sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  ALCOA FLAGS: [bullet list, or "None detected"]
  AUDIT-TRAIL FLAGS: [bullet list, or "None detected"]
  ATTRIBUTION FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
