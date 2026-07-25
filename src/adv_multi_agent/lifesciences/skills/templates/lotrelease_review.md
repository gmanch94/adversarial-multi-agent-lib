---
name: lotrelease_review
description: Reviewer criteria for a CGT lot-release specification adequacy audit; five-dimension scoring flagging SPEC-COVERAGE, SMALL-LOT, and SHELF-LIFE gaps (no veto)
inputs:
  - output
---
Evaluate this lot-release specification audit on five dimensions. Score each 0–10.

1. RELEASE-ATTRIBUTE COVERAGE (30%) — CRITICAL
   Does every release-critical attribute (identity, purity, potency, sterility,
   safety, viability) have an adequate specification with an acceptance criterion?
   Penalise a missing or inadequate specification. Flag under SPEC-COVERAGE FLAGS:.

2. SMALL-LOT SAMPLING (25%) — CRITICAL
   Is the sampling / test-consumption plan practical for the lot size, and do the
   acceptance criteria account for small-lot statistics? Penalise a plan that
   consumes the lot or ignores small-n. Flag under SMALL-LOT FLAGS:.

3. SHORT-SHELF-LIFE RELEASE (20%) — CRITICAL
   Is the rapid / real-time-release strategy for the short shelf life adequately
   justified (e.g. sterility / mycoplasma released before final results)? Penalise
   an unjustified release-before-result. Flag under SHELF-LIFE FLAGS:.

4. STABILITY & OUT-OF-SPECIFICATION HANDLING (15%)
   Do the stability program and out-of-specification handling support the claimed
   shelf life and disposition path? Penalise unsupported claims.

5. ACTIONABILITY (10%)
   Is each gap specific enough for QC to close (which attribute, which criterion,
   which method)? Penalise vague findings.

Overall score = weighted average.
Score >= 7.5 AND zero SPEC-COVERAGE FLAGS AND zero SMALL-LOT FLAGS AND zero
SHELF-LIFE FLAGS: ready for QC sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SPEC-COVERAGE FLAGS: [bullet list, or "None detected"]
  SMALL-LOT FLAGS: [bullet list, or "None detected"]
  SHELF-LIFE FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
