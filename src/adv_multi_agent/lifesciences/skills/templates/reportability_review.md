---
name: reportability_review
description: Reviewer criteria for a device-reportability determination; five-dimension scoring with D-LIFESCI-3 veto criteria for a non-reportable determination that is actually reportable
inputs:
  - output
---
Evaluate this device-reportability determination on five dimensions. Score each 0–10.

1. REPORTABILITY DETERMINATION (30%) — CRITICAL
   Does the event meet a reporting definition (death, serious injury, or a
   malfunction likely to cause/contribute to death or serious injury if it
   recurs)? Penalise a reportable event coded non-reportable. Flag under
   REPORTABILITY FLAGS:.

2. OUTCOME GRADING (25%) — CRITICAL
   Is the outcome graded correctly — is a reportable serious injury under-graded
   as minor? Penalise under-grading of patient impact. Flag under
   SERIOUS-INJURY FLAGS:.

3. MALFUNCTION TREND (20%) — CRITICAL
   Does a recurring malfunction cross a trend / threshold reporting trigger that
   the single event masks? Penalise a trend the determination ignores. Flag
   under MALFUNCTION-TREND FLAGS:.

4. REGULATORY-CLOCK FIT (15%)
   Is the statutory clock correct for the determination (21 CFR 803 timelines /
   regional vigilance)? Penalise an incorrect or unstated clock.

5. ACTIONABILITY (10%)
   Is the determination specific enough to act on (report path, clock, trend
   basis)? Penalise vague determinations.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a 'non-reportable' determination is actually reportable under
the applicable regulation (21 CFR 803 / regional vigilance).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero REPORTABILITY FLAGS AND zero SERIOUS-INJURY FLAGS AND
zero MALFUNCTION-TREND FLAGS AND no VETO: ready for Vigilance officer sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  REPORTABILITY FLAGS: [bullet list, or "None detected"]
  SERIOUS-INJURY FLAGS: [bullet list, or "None detected"]
  MALFUNCTION-TREND FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

DETERMINATION:
{output}
