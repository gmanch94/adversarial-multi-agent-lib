---
name: stability_review
description: Reviewer criteria for a stability / shelf-life justification review; EXTRAPOLATION + TREND + SPEC-EXCEEDANCE flags
inputs:
  - output
---

Evaluate this stability / shelf-life review on five dimensions. Score each 0–10.

1. EXTRAPOLATION JUSTIFICATION (30%) — CRITICAL
   Is the proposed shelf life justified by the available long-term (and
   supporting accelerated) data under ICH Q1E, not extrapolated beyond what the
   data and the guidance allow? Penalise extrapolation the data cannot support.
   Flag under EXTRAPOLATION FLAGS:.

2. TREND ANALYSIS (25%) — CRITICAL
   Does the review account for any downward or degradation trend across
   timepoints (assay, impurities, dissolution)? Penalise a trend the proposal
   ignores or dismisses. Flag under TREND FLAGS:.

3. SPECIFICATION CONFORMANCE (20%) — CRITICAL
   Are all results within specification, and is any at/over-specification result
   investigated rather than treated as passing? Penalise an OOS/OOT treated as a
   pass. Flag under SPEC-EXCEEDANCE FLAGS:.

4. STATISTICAL-MODEL FIT (15%)
   Is the statistical approach (regression, poolability of batches per ICH Q1E)
   appropriate for the data? Penalise pooling or modeling that the data do not
   justify.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which attribute, which timepoint,
   which batch)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero EXTRAPOLATION FLAGS AND zero TREND FLAGS AND zero
SPEC-EXCEEDANCE FLAGS: ready for Stability / Analytical Sciences sign-off.
Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  EXTRAPOLATION FLAGS: [bullet list, or "None detected"]
  TREND FLAGS: [bullet list, or "None detected"]
  SPEC-EXCEEDANCE FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
