---
name: pvsignal_review
description: Reviewer criteria for a pharmacovigilance signal evaluation; SIGNAL-STRENGTH + CAUSALITY + LABELING-IMPACT flags with an under-escalation veto
inputs:
  - output
---

Evaluate this pharmacovigilance signal evaluation on five dimensions. Score each 0–10.

1. SIGNAL STRENGTH (30%) — CRITICAL
   Is the signal strength correctly characterized against the disproportionality
   metrics and case evidence? Penalise a signal strength understated relative to
   the evidence. Flag under SIGNAL-STRENGTH FLAGS:.

2. CAUSALITY ASSESSMENT (25%) — CRITICAL
   Is population-level causality assessed with an adequate basis (not dismissed)?
   Penalise causality dismissed without adequate justification. Flag under
   CAUSALITY FLAGS:.

3. LABELING/REGULATORY IMPACT (20%) — CRITICAL
   Does the proposed action reflect the labeling / regulatory implication of the
   signal? Penalise a labeling / regulatory-action implication the proposed
   action does not reflect. Flag under LABELING-IMPACT FLAGS:.

4. BENEFIT-RISK / DATA-SOURCE ADEQUACY (15%)
   Is the data source adequate for the conclusion and the benefit-risk framing
   sound? Penalise a conclusion the data source cannot support.

5. ACTIONABILITY (10%)
   Is the evaluation specific enough to act on (signal, metric, action)? Penalise
   vague evaluations.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a signal meeting the threshold for regulatory action / label
change is characterized as no-action / routine.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SIGNAL-STRENGTH FLAGS AND zero CAUSALITY FLAGS AND zero
LABELING-IMPACT FLAGS AND no VETO: ready for Safety Physician sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SIGNAL-STRENGTH FLAGS: [bullet list, or "None detected"]
  CAUSALITY FLAGS: [bullet list, or "None detected"]
  LABELING-IMPACT FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
