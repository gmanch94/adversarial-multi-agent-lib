---
name: ccds_review
description: Reviewer criteria for a CCDS safety label-change review; SAFETY-SIGNAL + REGIONAL-DIVERGENCE + IMPLEMENTATION-CLOCK flags with a fails-to-convey-the-risk veto
inputs:
  - output
---

Evaluate this CCDS safety label-change review on five dimensions. Score each 0–10.

1. SIGNAL-TO-LABEL FIDELITY (30%) — CRITICAL
   Does the proposed CCDS wording convey the established safety signal faithfully,
   with no safety implication understated or omitted? Penalise wording that
   understates the signal. Flag under SAFETY-SIGNAL FLAGS:.

2. REGIONAL CONSISTENCY (25%) — CRITICAL
   Does every regional/local label reflect the CCDS change, with any divergence
   justified and no market missed? Penalise an unjustified divergence or a missed
   market. Flag under REGIONAL-DIVERGENCE FLAGS:.

3. TIMELINE COMPLIANCE (20%) — CRITICAL
   Does the plan meet every mandatory regulatory notification/submission clock for
   the safety change? Penalise a timeline the plan will miss. Flag under
   IMPLEMENTATION-CLOCK FLAGS:.

4. BENEFIT-RISK COHERENCE (15%)
   Is the wording proportionate to the signal and the population-level
   benefit-risk? Penalise wording out of proportion to the signal.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which wording, which region, which
   clock)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the plan omits or materially understates an established serious
safety signal in the safety labeling, OR misses a mandatory regulatory
notification clock for a safety change. Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero SAFETY-SIGNAL FLAGS AND zero REGIONAL-DIVERGENCE FLAGS AND
zero IMPLEMENTATION-CLOCK FLAGS AND no VETO: ready for Global Labeling sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  SAFETY-SIGNAL FLAGS: [bullet list, or "None detected"]
  REGIONAL-DIVERGENCE FLAGS: [bullet list, or "None detected"]
  IMPLEMENTATION-CLOCK FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
