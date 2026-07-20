---
name: rems_review
description: Reviewer criteria for a REMS design review; RISK-MITIGATION + BURDEN + ASSESSMENT-PLAN flags
inputs:
  - output
---

Evaluate this REMS design on five dimensions. Score each 0–10.

1. RISK-TO-ELEMENT FIT (30%) — CRITICAL
   Does every REMS element (Medication Guide, communication plan, ETASU) map to
   a serious risk it must mitigate, and does every serious risk have a mitigating
   element? Penalise an element with no matching risk, or a risk with no element.
   Flag each mismatch under RISK-MITIGATION FLAGS:.

2. ACCESS-BURDEN PROPORTIONALITY (25%) — CRITICAL
   Is each element's burden on patient access, providers, and the supply chain
   proportionate to the risk it mitigates? Penalise an element imposing
   disproportionate burden relative to the risk. Flag under BURDEN FLAGS:.

3. ASSESSMENT ADEQUACY (20%) — CRITICAL
   Do the assessment metrics and timetable actually measure whether the REMS
   meets its goals (risk reduction)? Penalise metrics/timetable that cannot show
   goal attainment. Flag gaps under ASSESSMENT-PLAN FLAGS:.

4. IMPLEMENTATION FEASIBILITY (15%)
   Are the elements operable in the real prescribing/dispensing supply chain?
   Penalise elements that cannot be implemented as described.

5. ACTIONABILITY (10%)
   Is each finding specific enough for the REMS lead to act on (which element,
   which risk, which metric)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero RISK-MITIGATION FLAGS AND zero BURDEN FLAGS AND zero
ASSESSMENT-PLAN FLAGS: ready for REMS lead sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  RISK-MITIGATION FLAGS: [bullet list, or "None detected"]
  BURDEN FLAGS: [bullet list, or "None detected"]
  ASSESSMENT-PLAN FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
