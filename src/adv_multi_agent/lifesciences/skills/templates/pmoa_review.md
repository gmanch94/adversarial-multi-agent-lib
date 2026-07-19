---
name: pmoa_review
description: Reviewer criteria for a combination-product PMOA analysis; PMOA + LEAD-CENTER + PATHWAY flags
inputs:
  - output
---

Evaluate this combination-product PMOA analysis on five dimensions. Score each 0–10.

1. PMOA DETERMINATION (30%) — CRITICAL
   Is the primary mode of action consistent with the described therapeutic
   mechanism and each constituent's contribution? Penalise a PMOA that does not
   follow from the mechanism (e.g. a drug PMOA where the device provides the
   primary therapeutic effect). Flag under PMOA FLAGS:.

2. LEAD-CENTER ASSIGNMENT (25%) — CRITICAL
   Does the proposed lead center (CDER / CBER / CDRH) follow from the PMOA?
   Penalise a center assignment inconsistent with the determined PMOA. Flag
   under LEAD-CENTER FLAGS:.

3. PATHWAY CONSISTENCY (20%) — CRITICAL
   Is the proposed submission pathway (NDA / BLA / PMA / 510(k)) consistent with
   the center and PMOA? Penalise a pathway that does not match. Flag under
   PATHWAY FLAGS:.

4. PRECEDENT ALIGNMENT (15%)
   Do cited precedent products / RFD determinations actually support the
   proposed routing? Penalise precedents that are not analogous.

5. ACTIONABILITY (10%)
   Is the recommendation specific enough for a regulatory strategist to act on
   (which center, which pathway, which precedent)? Penalise vague routing.

Overall score = weighted average.
Score >= 7.5 AND zero PMOA FLAGS AND zero LEAD-CENTER FLAGS AND zero PATHWAY
FLAGS: ready for Regulatory Strategy sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  PMOA FLAGS: [bullet list, or "None detected"]
  LEAD-CENTER FLAGS: [bullet list, or "None detected"]
  PATHWAY FLAGS: [bullet list, or "None detected"]

ANALYSIS:
{output}
