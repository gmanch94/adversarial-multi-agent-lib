---
name: protocol_review
description: Reviewer criteria for a clinical protocol design review; ENDPOINT + POWER + SAFETY-MONITORING flags with a subject-risk / invalid-objective veto
inputs:
  - output
---

Evaluate this clinical protocol design review on five dimensions. Score each 0–10.

1. ENDPOINT VALIDITY (30%) — CRITICAL
   Is the primary endpoint validated and able to support the study objective (no
   misused surrogate)? Penalise an endpoint that cannot support the objective.
   Flag under ENDPOINT FLAGS:.

2. STATISTICAL POWER (25%) — CRITICAL
   Is the sample size and power adequate to detect the effect, with justified
   assumptions? Penalise an underpowered design or unjustified effect-size
   assumptions. Flag under POWER FLAGS:.

3. SAFETY MONITORING (20%) — CRITICAL
   Are the safety-monitoring plan and stopping rules adequate for the known
   risks (DSMB, pre-specified stopping rules)? Penalise inadequate monitoring for
   a known serious risk. Flag under SAFETY-MONITORING FLAGS:.

4. ETHICS / POPULATION-APPROPRIATENESS (15%)
   Is the eligibility appropriate and proportionate to the risk, with safeguards
   for any vulnerable population? Penalise eligibility that exposes subjects
   without justification.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which endpoint, which assumption,
   which stopping rule)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the protocol exposes subjects to undue risk (inadequate safety
monitoring / stopping rules for a known serious risk) or is scientifically
invalid such that it cannot support its primary objective.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero ENDPOINT FLAGS AND zero POWER FLAGS AND zero
SAFETY-MONITORING FLAGS AND no VETO: ready for Clinical Development sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  ENDPOINT FLAGS: [bullet list, or "None detected"]
  POWER FLAGS: [bullet list, or "None detected"]
  SAFETY-MONITORING FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
