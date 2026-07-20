---
name: biosimilar_review
description: Reviewer criteria for a biosimilar comparability assessment; ANALYTICAL-SIMILARITY + RESIDUAL-UNCERTAINTY + BRIDGING flags with an unsupported-biosimilarity-conclusion veto
inputs:
  - output
---

Evaluate this biosimilar comparability assessment on five dimensions. Score each 0–10.

1. ANALYTICAL SIMILARITY (30%) — CRITICAL
   Is every critical quality attribute (CQA) demonstrated analytically similar to
   the reference product within a justified range? Penalise a CQA not demonstrated
   similar. Flag under ANALYTICAL-SIMILARITY FLAGS:.

2. RESIDUAL-UNCERTAINTY RESOLUTION (25%) — CRITICAL
   Is the residual uncertainty after analytical/functional data honestly stated
   and resolved by the totality of evidence (PK/PD, clinical, immunogenicity)?
   Penalise understated or unresolved residual uncertainty. Flag under
   RESIDUAL-UNCERTAINTY FLAGS:.

3. BRIDGING & EXTRAPOLATION (20%) — CRITICAL
   Is every bridging step and every extrapolated indication justified by the
   comparability data? Penalise an unjustified bridge or extrapolation. Flag under
   BRIDGING FLAGS:.

4. TOTALITY-OF-EVIDENCE COHERENCE (15%)
   Is the stepwise evidence integrated into a coherent totality-of-evidence
   argument? Penalise a conclusion that ignores a weak step.

5. ACTIONABILITY (10%)
   Is each finding specific enough to act on (which CQA, which study, which
   indication)? Penalise vague findings.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if a biosimilarity conclusion (or indication extrapolation) is
asserted while a critical quality attribute is not demonstrated analytically
similar and the residual uncertainty is unresolved.
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those as
  stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero ANALYTICAL-SIMILARITY FLAGS AND zero RESIDUAL-UNCERTAINTY
FLAGS AND zero BRIDGING FLAGS AND no VETO: ready for Regulatory Affairs sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  ANALYTICAL-SIMILARITY FLAGS: [bullet list, or "None detected"]
  RESIDUAL-UNCERTAINTY FLAGS: [bullet list, or "None detected"]
  BRIDGING FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">

REVIEW:
{output}
