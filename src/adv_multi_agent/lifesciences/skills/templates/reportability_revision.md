---
name: reportability_revision
description: Revision prompt for a device-reportability determination; addresses REPORTABILITY FLAGS, SERIOUS-INJURY FLAGS, MALFUNCTION-TREND FLAGS from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this device-reportability determination. Address EVERY issue in the
reviewer's critique, especially any REPORTABILITY FLAGS, SERIOUS-INJURY FLAGS, or
MALFUNCTION-TREND FLAGS.

PREVIOUS DETERMINATION:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (Event summary, Reportability
determination, Outcome grading, Malfunction-trend assessment, Statutory clock and
report path, Claims).

For every REPORTABILITY FLAG: re-apply the reporting definition (death, serious
injury, or malfunction likely to cause/contribute to serious injury if it
recurs) and state the statutory clock. Do not code a reportable event as
non-reportable.

For every SERIOUS-INJURY FLAG: re-grade the outcome against the serious-injury
definition. Do not under-grade a reportable outcome as minor.

For every MALFUNCTION-TREND FLAG: account for prior_similar_events_count against
the trend / threshold reporting trigger. Do not let a single-event view mask a
reportable trend.
