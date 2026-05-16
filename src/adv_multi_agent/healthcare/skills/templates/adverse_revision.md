---
name: adverse_revision
description: Revision prompt for adverse-event triage; addresses SEVERITY FLAGS, CAUSALITY FLAGS, REGULATORY FLAGS from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this adverse-event triage. Address EVERY issue in the reviewer's
critique, especially any SEVERITY FLAGS, CAUSALITY FLAGS, or REGULATORY FLAGS.

PREVIOUS TRIAGE:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Severity assessment, Causality
analysis, Regulatory-obligation determination, MedDRA coding, Recommended
action, Claims).

For every SEVERITY FLAG: re-grade against CTCAE / ICH E2A definitions;
do not use general practice intuition or infer beyond the reporter's narrative.

For every CAUSALITY FLAG: cite the specific WHO-UMC or Naranjo criterion
(temporal relationship, dechallenge, rechallenge, alternative cause ruled out);
do not assert causality without a named scale.

For every REGULATORY FLAG: match obligation to FDA 21 CFR 312 / EMA
EudraVigilance / ICH E2A reporting clock explicitly (7-day for
fatal/life-threatening unexpected; 15-day for other serious unexpected).
