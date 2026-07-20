---
name: serialization_review
description: Reviewer criteria for a serialization / DSCSA traceability review; AGGREGATION + TRACEABILITY + SALEABLE-RETURN flags
inputs:
  - output
---

Evaluate this serialization / DSCSA traceability review on five dimensions. Score each 0–10.

1. AGGREGATION INTEGRITY (30%) — CRITICAL
   Is every parent-child aggregation link across packaging tiers (item / case /
   pallet) present and correct? Penalise a broken or missing aggregation link.
   Flag under AGGREGATION FLAGS:.

2. EVENT / TRACEABILITY COVERAGE (25%) — CRITICAL
   Is every required EPCIS event and trading-partner data element present, so
   unit-level traceability is unbroken? Penalise a missing event or data element.
   Flag under TRACEABILITY FLAGS:.

3. SALEABLE-RETURN VERIFICATION (20%) — CRITICAL
   Is every saleable return verified at the product-identifier (unit) level before
   resale? Penalise a saleable return processed without the required verification.
   Flag under SALEABLE-RETURN FLAGS:.

4. INTEROPERABILITY READINESS (15%)
   Is the system ready for enhanced unit-level traceability and interoperable
   exchange? Penalise gaps in interoperability capability.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which tier, which event, which
   return)? Penalise vague findings.

Overall score = weighted average.
Score >= 7.5 AND zero AGGREGATION FLAGS AND zero TRACEABILITY FLAGS AND zero
SALEABLE-RETURN FLAGS: ready for Supply-Chain Compliance sign-off. Otherwise:
requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  AGGREGATION FLAGS: [bullet list, or "None detected"]
  TRACEABILITY FLAGS: [bullet list, or "None detected"]
  SALEABLE-RETURN FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
