---
name: hctp_review
description: Reviewer criteria for an HCT/P regulatory-tier classification; five-dimension scoring across all four 1271.10(a) prongs with D-LIFESCI-8 veto for a 351 biologic asserted as 361
inputs:
  - output
---
Evaluate this HCT/P regulatory-tier classification on five dimensions. Score each 0–10.
A 361 HCT/P must satisfy ALL FOUR 21 CFR 1271.10(a) prongs; assess each.

1. MINIMAL MANIPULATION — prong (1) (30%) — CRITICAL
   Does processing keep the cells/tissue minimally manipulated (relevant
   biological characteristics unaltered for structural tissue; relevant
   characteristics unaltered for cells)? Penalise processing that alters the
   relevant characteristics. Flag under MINIMAL-MANIPULATION FLAGS.

2. HOMOLOGOUS USE — prong (2) (25%) — CRITICAL
   Is the intended use homologous to the tissue's original basic function?
   Penalise a non-homologous intended use. Flag under HOMOLOGOUS-USE FLAGS.

3. TIER CLASSIFICATION — prongs (3) and (4) plus the overall call (25%) — CRITICAL
   Prong (3): is the product NOT combined with another article (except water,
   crystalloids, or a sterilizing / preserving / storage agent)? Prong (4): is
   there NO systemic effect and NO dependence on the metabolic activity of living
   cells (unless autologous / first- or second-degree relative / reproductive
   use)? Does the overall 361-vs-351 call follow from all four prongs? Penalise a
   disqualifying combination, a systemic effect, or a 361 call that ignores a
   failed prong. Flag under TIER-CLASSIFICATION FLAGS.

4. PRECEDENT CONSISTENCY (10%)
   Is the tier consistent with cited regulatory precedent for comparable products?
   Penalise a call inconsistent with precedent.

5. ACTIONABILITY (10%)
   Is each finding specific enough for RA to resolve (which prong, which
   processing step, which use)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a 351 biologic is asserted as a 361 HCT/P — more-than-minimal
manipulation, non-homologous use, a disqualifying combination, or a systemic
effect is present — such that the 361 call would bypass the BLA and misrepresent
regulatory status.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero MINIMAL-MANIPULATION FLAGS AND zero HOMOLOGOUS-USE FLAGS AND
zero TIER-CLASSIFICATION FLAGS AND no VETO: ready for Regulatory Affairs sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  MINIMAL-MANIPULATION FLAGS: [bullet list, or "None detected"]
  HOMOLOGOUS-USE FLAGS: [bullet list, or "None detected"]
  TIER-CLASSIFICATION FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
