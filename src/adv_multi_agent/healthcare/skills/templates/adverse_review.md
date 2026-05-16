---
name: adverse_review
description: Reviewer criteria for adverse-event triage; five-dimension scoring with D-HEALTH-4 veto criteria citing FDA 21 CFR 312 / ICH E2A / EMA EudraVigilance
inputs:
  - output
---
Evaluate this adverse-event triage on five dimensions. Score each 0–10.

1. SEVERITY GRADING (30%) — CRITICAL
   Is the event graded against CTCAE / ICH E2A definitions, NOT general
   practice intuition? Are grade assignments consistent with reporter's
   narrative? Penalise severity claims not anchored to CTCAE or ICH E2A.
   Flag gaps under SEVERITY FLAGS:.

2. CAUSALITY ASSESSMENT (25%) — CRITICAL
   Is WHO-UMC or Naranjo causality scale applied? Are specific criteria cited
   (temporal relationship, dechallenge/rechallenge, alternative cause ruled
   out)? Penalise causality assertions not grounded in a named scale.
   Flag gaps under CAUSALITY FLAGS:.

3. REGULATORY-OBLIGATION FIT (20%) — CRITICAL
   Is the reporting obligation matched to FDA 21 CFR 312 / EMA EudraVigilance /
   ICH E2A reporting clock? (7-day for fatal/life-threatening unexpected;
   15-day for other serious unexpected.) Does the triage correctly identify
   whether the ADR is in current labeling? Flag gaps under REGULATORY FLAGS:.

4. MedDRA CODING ACCURACY (15%)
   Is the preferred-term / system-organ-class alignment plausible for the
   event described? Penalise PT/SOC combinations that conflict with the
   event narrative.

5. ACTIONABILITY (10%)
   Is the report path and regulatory clock specified? Vague recommendations
   ("report as required") should be flagged.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Serious unexpected ADR (not in current product labeling per prior_reports)
    with causality ≥ possible → mandatory FDA 21 CFR 312 / EMA EudraVigilance
    expedited report required (15-day clock for serious unexpected; 7-day
    for fatal/life-threatening unexpected per ICH E2A).
  • Fatal outcome with causality ≥ possible AND event not in current
    labeling → 7-day expedited reporting clock.
  • Life-threatening outcome with causality ≥ probable → 7-day expedited
    reporting clock.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those
  as stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score ≥ 8.0 AND zero SEVERITY FLAGS AND zero CAUSALITY FLAGS AND zero
REGULATORY FLAGS AND no VETO: triage is ready for pharmacovigilance officer
sign-off. Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SEVERITY FLAGS: [bullet list, or "None detected"]
  CAUSALITY FLAGS: [bullet list, or "None detected"]
  REGULATORY FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
