---
name: se510k_review
description: Reviewer criteria for substantial-equivalence 510(k) rationale; five-dimension scoring with D-LIFESCI-2 veto criteria for a fundamentally unsupportable SE claim (near-certain NSE)
inputs:
  - output
---
Evaluate this substantial-equivalence rationale on five dimensions. Score each 0–10.

1. PREDICATE VALIDITY (30%) — CRITICAL
   Does the candidate predicate share the same intended use and device type,
   making it a valid SE anchor? Penalise a predicate with a different intended
   use or device type. Flag under PREDICATE-MISMATCH FLAGS:.

2. INDICATIONS SCOPE (25%) — CRITICAL
   Are the subject device's indications-for-use within the predicate's cleared
   indications? Penalise indications broader than the predicate's. Flag under
   INDICATION-CREEP FLAGS:.

3. TECHNOLOGICAL DIFFERENCES (20%) — CRITICAL
   Do new technological characteristics raise new questions of safety or
   effectiveness (the Not-Substantially-Equivalent trigger)? Penalise a
   difference that raises a new question but is argued away. Flag under
   TECHNOLOGY-DELTA FLAGS:.

4. PERFORMANCE-DATA SUFFICIENCY (15%)
   Do the performance data actually address each identified difference?
   Penalise differences with no supporting data.

5. ACTIONABILITY (10%)
   Is each finding specific enough for RA to resolve (which predicate, which
   indication, which characteristic)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the substantial-equivalence claim is fundamentally unsupportable
(near-certain NSE — no valid predicate, or a technological difference that
plainly raises a new question of safety/effectiveness) such that asserting SE
would misrepresent equivalence to FDA.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero PREDICATE-MISMATCH FLAGS AND zero INDICATION-CREEP FLAGS
AND zero TECHNOLOGY-DELTA FLAGS AND no VETO: ready for Regulatory Affairs
sign-off. Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PREDICATE-MISMATCH FLAGS: [bullet list, or "None detected"]
  INDICATION-CREEP FLAGS: [bullet list, or "None detected"]
  TECHNOLOGY-DELTA FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
