---
name: heor_review
description: Reviewer criteria for an HEOR value-dossier review; COMPARATOR + ENDPOINT-RELEVANCE + EXTRAPOLATION flags
inputs:
  - output
---

Evaluate this HEOR value dossier on five dimensions. Score each 0–10.

1. COMPARATOR APPROPRIATENESS (30%) — CRITICAL
   Is every comparator appropriate to the decision problem and the target market
   (current standard of care)? Penalise an inappropriate or missing comparator.
   Flag under COMPARATOR FLAGS:.

2. ENDPOINT RELEVANCE (25%) — CRITICAL
   Does the dossier rely on patient-relevant final endpoints where required, or
   justify any surrogate/intermediate endpoint? Penalise an unjustified surrogate
   used in place of a final endpoint. Flag under ENDPOINT-RELEVANCE FLAGS:.

3. EXTRAPOLATION VALIDITY (20%) — CRITICAL
   Are the model extrapolations and assumptions supported by the evidence and not
   over-optimistic? Penalise an unsupported or optimistic extrapolation. Flag
   under EXTRAPOLATION FLAGS:.

4. MODEL TRANSPARENCY / EVIDENCE FIT (15%)
   Are model assumptions sourced and the model structure justified against the
   evidence? Penalise opaque or poorly-fitted modeling.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which comparator, which endpoint,
   which assumption)? Penalise vague findings.

Overall score = weighted average.
Score >= 7.5 AND zero COMPARATOR FLAGS AND zero ENDPOINT-RELEVANCE FLAGS AND zero
EXTRAPOLATION FLAGS: ready for HEOR lead sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  COMPARATOR FLAGS: [bullet list, or "None detected"]
  ENDPOINT-RELEVANCE FLAGS: [bullet list, or "None detected"]
  EXTRAPOLATION FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
