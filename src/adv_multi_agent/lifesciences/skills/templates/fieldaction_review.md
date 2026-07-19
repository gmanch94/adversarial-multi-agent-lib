---
name: fieldaction_review
description: Reviewer criteria for a field-action classification; five-dimension scoring with D-LIFESCI-3 veto criteria for a recall-class downgrade or 'not reportable' call that leaves patients exposed
inputs:
  - output
---
Evaluate this field-action classification on five dimensions. Score each 0–10.

1. RECALL CLASSIFICATION (30%) — CRITICAL
   Is the proposed recall class consistent with the health hazard? Penalise a
   Class II proposed where a reasonable probability of serious adverse health
   consequences indicates Class I. Flag under RECALL-CLASS FLAGS:.

2. CORRECTION-REMOVAL REPORTABILITY (25%) — CRITICAL
   Is a 21 CFR 806 reportable correction/removal correctly characterised, and
   not mislabelled as a non-reportable enhancement or routine stock recovery?
   Penalise a reportable action characterised as non-reportable. Flag under
   CORRECTION-REMOVAL FLAGS:.

3. HEALTH-HAZARD EVALUATION (20%) — CRITICAL
   Does the health-hazard evaluation state probability, severity, and affected
   population without understating any? Penalise an evaluation that understates
   the hazard. Flag under HEALTH-HAZARD FLAGS:.

4. SCOPE COMPLETENESS (15%)
   Are affected lots/serials and distribution scope complete for the root cause?
   Penalise an under-scoped lot/distribution list.

5. ACTIONABILITY (10%)
   Is the classification specific enough to act on (class, reportability call,
   scope)? Penalise vague classification.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a recall-class downgrade or a 'not reportable' call would leave
patients exposed to a hazard that the correct class/reportability would address.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero RECALL-CLASS FLAGS AND zero CORRECTION-REMOVAL FLAGS AND
zero HEALTH-HAZARD FLAGS AND no VETO: ready for Recall committee sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  RECALL-CLASS FLAGS: [bullet list, or "None detected"]
  CORRECTION-REMOVAL FLAGS: [bullet list, or "None detected"]
  HEALTH-HAZARD FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

CLASSIFICATION:
{output}
