---
name: vectorsafety_review
description: Reviewer criteria for a viral-vector genome-safety characterisation audit; five-dimension scoring flagging RCR-RCL-RISK, INSERTIONAL-MUTAGENESIS, and ONCOGENICITY gaps (no veto)
inputs:
  - output
---
Evaluate this vector-safety characterisation audit on five dimensions. Score each 0–10.

1. RCR/RCL TESTING ADEQUACY (30%) — CRITICAL
   Is the replication-competent retrovirus/lentivirus (RCR/RCL) testing strategy
   and sensitivity adequate for the vector class and dose? Penalise a strategy
   too insensitive, wrong-stage, or missing for the vector type. Flag under
   RCR-RCL-RISK FLAGS:.

2. INTEGRATION / INSERTIONAL-MUTAGENESIS (25%) — CRITICAL
   Is the integration-site / clonality assessment sufficient to characterise
   insertional-mutagenesis risk (integration profile, vector copy number,
   clonal-expansion monitoring)? Penalise gaps. Flag under
   INSERTIONAL-MUTAGENESIS FLAGS:.

3. ONCOGENICITY / TUMORIGENICITY (20%) — CRITICAL
   Is the oncogenicity / tumorigenicity evidence and the long-term-follow-up
   plan adequate for the risk profile? Penalise an under-powered or absent
   tumorigenicity case. Flag under ONCOGENICITY FLAGS:.

4. BIODISTRIBUTION & LONG-TERM FOLLOW-UP (15%)
   Do the nonclinical biodistribution data and the LTFU plan cover the persistence
   and shedding profile of the vector? Penalise unaddressed persistence.

5. ACTIONABILITY (10%)
   Is each gap specific enough for Biosafety to close (which assay, which endpoint,
   what sensitivity)? Penalise vague findings.

Overall score = weighted average.
Score >= 7.5 AND zero RCR-RCL-RISK FLAGS AND zero INSERTIONAL-MUTAGENESIS FLAGS
AND zero ONCOGENICITY FLAGS: ready for Biosafety sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  RCR-RCL-RISK FLAGS: [bullet list, or "None detected"]
  INSERTIONAL-MUTAGENESIS FLAGS: [bullet list, or "None detected"]
  ONCOGENICITY FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
