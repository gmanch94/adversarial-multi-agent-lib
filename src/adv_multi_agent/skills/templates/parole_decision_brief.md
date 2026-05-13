---
name: parole_decision_brief
description: Structure a completed parole assessment into a formal decision brief for the parole board
inputs: [risk_analysis, rehabilitation_evidence, reentry_plan, case_id]
---
You are preparing the final structured brief for the parole board for case {case_id}.
This brief is advisory only — the board makes the final decision.

RISK ANALYSIS:
{risk_analysis}

REHABILITATION EVIDENCE:
{rehabilitation_evidence}

REENTRY PLAN:
{reentry_plan}

Format a complete parole board brief with these sections:

---
# PAROLE ASSESSMENT BRIEF
**Case ID**: {case_id}
**Classification**: ADVISORY — NOT A DECISION
**Prepared by**: Adversarial AI Assessment System (adv-multi-agent)

⚠️ This brief is one structured input among many. The parole board must apply
independent judgment. This document must not be the sole basis for any decision.

---

## 1. Risk Summary
[2–3 sentence summary of key unresolved risk factors, drawn from Risk Analysis]

## 2. Rehabilitation Summary
[2–3 sentence summary of rehabilitation evidence credibility and strength]

## 3. Reentry Plan Summary
[2–3 sentence summary of reentry plan quality and gaps]

## 4. Advisory Recommendation
State: Grant / Conditional Grant / Deny
Reasoning: [2–3 sentences tying the recommendation to specific evidence above]

## 5. Recommended Conditions (if Grant or Conditional Grant)
[Numbered list of specific, enforceable conditions]

## 6. Evidence Gaps
[Bulleted list of missing information that would improve confidence]

## 7. Board Verification Checklist
[ ] Risk Analysis claims verified against original facility records
[ ] Rehabilitation programme certificates reviewed
[ ] Reentry plan contacts independently verified
[ ] Psychological assessment reviewed with licensed clinician
[ ] Victim notification procedures confirmed
[ ] Independent judgment applied — board not bound by advisory recommendation

---
⚠️ ADVISORY ONLY — AI-generated. Human determination required.
