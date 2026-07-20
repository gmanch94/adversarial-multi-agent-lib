---
name: coldchain_review
description: Reviewer criteria for a cold-chain excursion disposition; STABILITY-IMPACT + DISPOSITION + EXCURSION-SCOPE flags with a release-beyond-stability-budget veto
inputs:
  - output
---

Evaluate this cold-chain excursion disposition on five dimensions. Score each 0–10.

1. STABILITY-DATA JUSTIFICATION (30%) — CRITICAL
   Is the excursion's impact on potency/stability supported by stability data and
   the mean-kinetic-temperature (MKT) budget? Penalise an impact conclusion not
   supported by data. Flag under STABILITY-IMPACT FLAGS:.

2. DISPOSITION CONSISTENCY (25%) — CRITICAL
   Is the proposed disposition consistent with the stability-budget conclusion?
   Penalise a disposition that contradicts the stability finding. Flag under
   DISPOSITION FLAGS:.

3. EXCURSION-SCOPE COMPLETENESS (20%) — CRITICAL
   Is the affected-units scope and the cumulative excursion fully traced? Penalise
   an understated scope or an unsummed cumulative excursion. Flag under
   EXCURSION-SCOPE FLAGS:.

4. MKT / BUDGET RIGOR (15%)
   Is the cumulative excursion accounted for against the remaining stability
   budget with sound MKT reasoning? Penalise weak budget accounting.

5. ACTIONABILITY (10%)
   Is the disposition specific enough to act on (which lots, which budget, which
   disposition)? Penalise vague dispositions.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a 'release' disposition is proposed for product whose cumulative
excursion exceeds the stability budget (or has no supporting stability data).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero STABILITY-IMPACT FLAGS AND zero DISPOSITION FLAGS AND zero
EXCURSION-SCOPE FLAGS AND no VETO: ready for Quality sign-off. Otherwise: requires
revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  STABILITY-IMPACT FLAGS: [bullet list, or "None detected"]
  DISPOSITION FLAGS: [bullet list, or "None detected"]
  EXCURSION-SCOPE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
