---
name: durability_review
description: Reviewer criteria for a CGT durability / curative claim substantiation review; five-dimension scoring with D-LIFESCI-8 veto for a claim unsupported by the follow-up data
inputs:
  - output
---
Evaluate this durability / curative claim substantiation review on five dimensions.
Score each 0–10.

1. DURABILITY vs FOLLOW-UP DURATION (30%) — CRITICAL
   Does the durability claim stay within the observed follow-up duration and
   censoring? Penalise a claim that extends beyond the data. Flag under
   DURABILITY-CLAIM FLAGS:.

2. FOLLOW-UP EVIDENCE SUFFICIENCY (25%) — CRITICAL
   Are the n, median follow-up, and loss-of-response data sufficient to support
   the claimed persistence of effect? Penalise insufficient follow-up evidence.
   Flag under FOLLOWUP-EVIDENCE FLAGS:.

3. CURATIVE LANGUAGE (20%) — CRITICAL
   Is any "cure" / permanent-benefit language supported by the endpoint and data?
   Penalise curative language the endpoint cannot support. Flag under
   CURATIVE-LANGUAGE FLAGS:.

4. COMPARATOR / NATURAL-HISTORY CONTEXT (15%)
   Is the claim contextualised against a comparator or natural history? Penalise a
   claim with no comparator context where one is needed.

5. ACTIONABILITY (10%)
   Is each finding specific enough for Medical / Regulatory to resolve (which
   claim, which follow-up window, which endpoint)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the durability / curative claim is unsupported by the follow-up
duration and data — an overstatement with patient-harm / misbranding exposure.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero DURABILITY-CLAIM FLAGS AND zero FOLLOWUP-EVIDENCE FLAGS AND
zero CURATIVE-LANGUAGE FLAGS AND no VETO: ready for Regulatory + Medical sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  DURABILITY-CLAIM FLAGS: [bullet list, or "None detected"]
  FOLLOWUP-EVIDENCE FLAGS: [bullet list, or "None detected"]
  CURATIVE-LANGUAGE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
