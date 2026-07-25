---
name: comparability_review
description: Reviewer criteria for a CGT post-change comparability review; five-dimension scoring with D-LIFESCI-8 veto for a materially different product argued as comparable
inputs:
  - output
---
Evaluate this post-change comparability review on five dimensions. Score each 0–10.

1. PROCESS-CHANGE IMPACT (30%) — CRITICAL
   Does the change (process, site, vector lot, scale) plausibly affect a critical
   quality attribute? Penalise a change whose impact on a CQA is not addressed.
   Flag under PROCESS-DELTA FLAGS.

2. ANALYTICAL COMPARABILITY COVERAGE (25%) — CRITICAL
   Is the analytical panel sufficient (right attributes, right stage, adequately
   powered) to conclude comparability? Penalise a panel that cannot support the
   conclusion. Flag under ANALYTICAL-GAP FLAGS.

3. CLINICAL BRIDGING SUFFICIENCY (20%) — CRITICAL
   Where residual uncertainty remains, does the clinical bridging plan address it?
   Penalise residual uncertainty with no clinical bridge. Flag under
   CLINICAL-BRIDGE FLAGS.

4. RISK ASSESSMENT (15%)
   Does the risk assessment identify and rank the change's quality risks
   correctly? Penalise an understated risk assessment.

5. ACTIONABILITY (10%)
   Is each finding specific enough for CMC to resolve (which attribute, which
   method, which study)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO line containing a verbatim directive
if and only if the post-change product is not demonstrably comparable — the change
affects a critical quality attribute the package does not cover — such that
treating it as comparable would ship a materially different product without the
required new clinical data.
Otherwise: "None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero PROCESS-DELTA FLAGS AND zero ANALYTICAL-GAP FLAGS AND zero
CLINICAL-BRIDGE FLAGS AND no VETO: ready for Regulatory Affairs + CMC sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PROCESS-DELTA FLAGS: [bullet list, or "None detected"]
  ANALYTICAL-GAP FLAGS: [bullet list, or "None detected"]
  CLINICAL-BRIDGE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
