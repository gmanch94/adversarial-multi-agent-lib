---
name: udi_review
description: Reviewer criteria for a UDI labeling review; IDENTIFIER + GUDID-CONSISTENCY + PACKAGING-TIER flags
inputs:
  - output
---

Evaluate this UDI labeling review on five dimensions. Score each 0–10.

1. IDENTIFIER STRUCTURE (30%) — CRITICAL
   Is the DI/PI structure valid for the declared issuing agency (GS1 / HIBCC /
   ICCBBA), with the required production identifiers present? Penalise an invalid
   or incomplete identifier structure. Flag under IDENTIFIER FLAGS:.

2. GUDID/EUDAMED CONSISTENCY (25%) — CRITICAL
   Does every database attribute (GUDID / EUDAMED) match the label and artwork?
   Penalise a database attribute inconsistent with the label. Flag under
   GUDID-CONSISTENCY FLAGS:.

3. PACKAGING-TIER COVERAGE (20%) — CRITICAL
   Does every packaging tier that requires a UDI carry one, with the hierarchy DI
   relationships intact? Penalise a packaging tier missing its UDI or a broken
   hierarchy. Flag under PACKAGING-TIER FLAGS:.

4. LABEL-ARTWORK CONSISTENCY (15%)
   Are the human-readable and AIDC (barcode) forms consistent, and are
   direct-mark rules for reusable devices satisfied? Penalise HRI/AIDC mismatch.

5. ACTIONABILITY (10%)
   Is each finding specific enough to correct (which identifier, which attribute,
   which tier)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero IDENTIFIER FLAGS AND zero GUDID-CONSISTENCY FLAGS AND zero
PACKAGING-TIER FLAGS: ready for Regulatory Labeling sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  IDENTIFIER FLAGS: [bullet list, or "None detected"]
  GUDID-CONSISTENCY FLAGS: [bullet list, or "None detected"]
  PACKAGING-TIER FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
