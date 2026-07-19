---
name: batchrelease_review
description: Reviewer criteria for a batch-release deviation disposition; CRITICALITY + IMPACT-ASSESSMENT + RELEASE-RISK flags with a release-of-non-conforming-batch veto
inputs:
  - output
---

Evaluate this batch-release deviation disposition on five dimensions. Score each 0–10.

1. DEVIATION CRITICALITY (30%) — CRITICAL
   Is the deviation criticality (minor / major / critical) correct for its impact
   on the CQA and patient safety? Penalise a deviation under-classified relative
   to its CQA/safety impact. Flag under CRITICALITY FLAGS:.

2. IMPACT ASSESSMENT (25%) — CRITICAL
   Is the impact on product quality and safety fully assessed, with every
   affected CQA identified? Penalise an incomplete impact assessment or a missed
   affected CQA. Flag under IMPACT-ASSESSMENT FLAGS:.

3. RELEASE-RISK JUDGMENT (20%) — CRITICAL
   Does the proposed disposition leave unresolved risk to the patient or the CQA?
   Penalise a release with unresolved risk. Flag under RELEASE-RISK FLAGS:.

4. CAPA-LINKAGE / ROOT-CAUSE (15%)
   Is the root cause established and linked to an adequate CAPA? Penalise a
   disposition without a sound root cause or CAPA linkage.

5. ACTIONABILITY (10%)
   Is the disposition specific enough to act on (criticality, CQA, CAPA, release
   decision)? Penalise vague dispositions.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a 'release' disposition is proposed for a batch with an
unresolved critical deviation affecting a CQA or patient safety.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero CRITICALITY FLAGS AND zero IMPACT-ASSESSMENT FLAGS AND
zero RELEASE-RISK FLAGS AND no VETO: ready for Qualified Person sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  CRITICALITY FLAGS: [bullet list, or "None detected"]
  IMPACT-ASSESSMENT FLAGS: [bullet list, or "None detected"]
  RELEASE-RISK FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
