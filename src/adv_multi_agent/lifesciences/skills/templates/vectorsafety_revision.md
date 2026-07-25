---
name: vectorsafety_revision
description: Revision prompt for a viral-vector genome-safety characterisation audit; addresses RCR-RCL-RISK, INSERTIONAL-MUTAGENESIS, and ONCOGENICITY flags from reviewer critique
inputs:
  - previous
  - score
  - critique
  - suggestions
  - flag_section
  - wiki_context
---
Revise this vector-safety characterisation audit based on reviewer critique.
Address EVERY issue, especially any RCR-RCL-RISK FLAGS, INSERTIONAL-MUTAGENESIS
FLAGS, or ONCOGENICITY FLAGS.

ORIGINAL AUDIT:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure (RCR/RCL testing, Integration and
insertional-mutagenesis, Oncogenicity and tumorigenicity, Biodistribution and
long-term follow-up, Gaps and recommendations, Claims).

For every RCR-RCL-RISK FLAG: cite the missing or insensitive
replication-competent-virus assay for the named vector class; do not assert a
sensitivity the data do not show.

For every INSERTIONAL-MUTAGENESIS FLAG: cite the missing integration-site /
clonality endpoint; do not assert a characterisation absent from the input.

For every ONCOGENICITY FLAG: cite the missing tumorigenicity evidence or the
long-term-follow-up commitment; do not argue away an unaddressed risk.
