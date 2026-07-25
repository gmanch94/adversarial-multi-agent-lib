---
name: durability_revision
description: Revision prompt for a CGT durability / curative claim review; addresses DURABILITY-CLAIM, FOLLOWUP-EVIDENCE, and CURATIVE-LANGUAGE flags from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this durability / curative claim substantiation review. Address EVERY issue
in the reviewer's critique, especially any DURABILITY-CLAIM FLAGS, FOLLOWUP-EVIDENCE
FLAGS, or CURATIVE-LANGUAGE FLAGS.

PREVIOUS REVIEW:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Durability vs follow-up, Follow-up
evidence, Curative language, Comparator / natural-history context, Claim
conclusion, Claims).

For every DURABILITY-CLAIM FLAG: narrow the durability claim to the observed
follow-up window, or acknowledge it is unsupported.

For every FOLLOWUP-EVIDENCE FLAG: cite the follow-up n / duration that supports
persistence, or acknowledge the evidence is insufficient.

For every CURATIVE-LANGUAGE FLAG: remove or qualify curative language the endpoint
cannot support.
