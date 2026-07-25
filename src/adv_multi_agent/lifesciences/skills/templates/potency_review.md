---
name: potency_review
description: Reviewer criteria for a CGT potency-assay lot-release adequacy review; five-dimension scoring with D-LIFESCI-8 veto criteria for an assay inadequate to support release
inputs:
  - output
---
Evaluate this potency-assay adequacy review on five dimensions. Score each 0–10.

1. MECHANISM-OF-ACTION LINKAGE (30%) — CRITICAL
   Is the assay readout demonstrably linked to the product's mechanism of action
   / clinical activity? Penalise a readout that measures a surrogate not tied to
   activity. Flag under MOA-LINKAGE FLAGS:.

2. LOT-RELEASE CLAIM SUPPORT (25%) — CRITICAL
   Does the assay plus its acceptance criteria actually support the stated
   lot-release claim? Penalise a claim beyond what the assay supports. Flag under
   LOT-RELEASE-CLAIM FLAGS:.

3. ASSAY VALIDATION (20%) — CRITICAL
   Is the assay validated for a release-critical method (accuracy, precision,
   specificity, range, stability-indicating capability)? Penalise inadequate
   validation. Flag under ASSAY-VALIDATION FLAGS:.

4. SURROGATE / MATRIX JUSTIFICATION (15%)
   If a surrogate readout or a matrix substitution is used, is it justified?
   Penalise an unjustified surrogate.

5. ACTIONABILITY (10%)
   Is each finding specific enough for CMC to resolve (which readout, which
   criterion, which validation element)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the potency assay is inadequate to support lot release — the
readout is not linked to clinical activity, or validation is insufficient for a
release-critical method — such that releasing on it risks releasing product
without demonstrated activity.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero MOA-LINKAGE FLAGS AND zero LOT-RELEASE-CLAIM FLAGS AND zero
ASSAY-VALIDATION FLAGS AND no VETO: ready for CMC + QE sign-off. Otherwise:
requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  MOA-LINKAGE FLAGS: [bullet list, or "None detected"]
  LOT-RELEASE-CLAIM FLAGS: [bullet list, or "None detected"]
  ASSAY-VALIDATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
