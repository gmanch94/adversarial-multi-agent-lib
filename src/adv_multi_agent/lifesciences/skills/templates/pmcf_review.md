---
name: pmcf_review
description: Reviewer criteria for a PMCF adequacy review; EVIDENCE-GAP + RESIDUAL-RISK + PMCF-ADEQUACY flags
inputs:
  - output
---

Evaluate this PMCF adequacy review on five dimensions. Score each 0–10.

1. EVIDENCE SUFFICIENCY (30%) — CRITICAL
   Is every claimed clinical benefit and indication supported by sufficient
   post-market evidence? Penalise a claim with insufficient evidence. Flag under
   EVIDENCE-GAP FLAGS:.

2. RESIDUAL-RISK COVERAGE (25%) — CRITICAL
   Does every residual risk have a PMCF activity that confirms or monitors it?
   Penalise a residual risk with no covering activity. Flag under
   RESIDUAL-RISK FLAGS:.

3. PMCF-METHOD ADEQUACY (20%) — CRITICAL
   Is each PMCF method (study, registry, literature, real-world data) adequate to
   answer its stated objective and detect the risk? Penalise a method that cannot
   answer its objective. Flag under PMCF-ADEQUACY FLAGS:.

4. BENEFIT-RISK / PMS INTEGRATION (15%)
   Do the PMCF outputs feed the benefit-risk determination and the PSUR/PMS
   system? Penalise a PMCF that does not integrate with post-market surveillance.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which claim, which risk, which
   method)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero EVIDENCE-GAP FLAGS AND zero RESIDUAL-RISK FLAGS AND zero
PMCF-ADEQUACY FLAGS: ready for Clinical Affairs sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  EVIDENCE-GAP FLAGS: [bullet list, or "None detected"]
  RESIDUAL-RISK FLAGS: [bullet list, or "None detected"]
  PMCF-ADEQUACY FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
