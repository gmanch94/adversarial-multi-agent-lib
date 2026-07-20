---
name: medinfo_review
description: Reviewer criteria for a medical-information response review; OFF-LABEL + BALANCE + EVIDENCE-LEVEL flags with a promotes-an-off-label-use veto
inputs:
  - output
---

Evaluate this medical-information response on five dimensions. Score each 0–10.

1. OFF-LABEL BOUNDARY (30%) — CRITICAL
   Does every off-label statement stay within a truthful, non-promotional,
   evidence-based answer to the SPECIFIC unsolicited question? Penalise an
   off-label statement that exceeds the question and crosses into promotion. Flag
   under OFF-LABEL FLAGS:.

2. FAIR BALANCE (25%) — CRITICAL
   Is efficacy presented with fair balance of risk and limitation? Penalise
   efficacy stated without the corresponding risk/limitation. Flag under
   BALANCE FLAGS:.

3. EVIDENCE CALIBRATION (20%) — CRITICAL
   Is every claim stated no more strongly than its evidence level supports?
   Penalise a claim stronger than its evidence. Flag under EVIDENCE-LEVEL FLAGS:.

4. RESPONSIVENESS / NON-PROMOTIONAL TONE (15%)
   Does the response answer the actual question in a scientific, non-promotional
   tone? Penalise a response that is unresponsive or promotional in tone.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which statement, which risk, which
   claim)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if the response crosses from a truthful, balanced, reactive
scientific exchange into PROMOTION of an off-label use. Otherwise:
"REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero OFF-LABEL FLAGS AND zero BALANCE FLAGS AND zero
EVIDENCE-LEVEL FLAGS AND no VETO: ready for Medical Information sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  OFF-LABEL FLAGS: [bullet list, or "None detected"]
  BALANCE FLAGS: [bullet list, or "None detected"]
  EVIDENCE-LEVEL FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
