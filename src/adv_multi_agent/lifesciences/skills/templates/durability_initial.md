---
name: durability_initial
description: Initial CGT durability / curative claim substantiation review; assesses durability vs follow-up, follow-up evidence, and curative language against the supplied data
inputs:
  - product_description
  - proposed_claim
  - pivotal_efficacy_summary
  - followup_duration_and_n
  - durability_evidence
  - population_and_endpoint
  - comparator_or_natural_history
  - label_context
---
You are substantiating a proposed durability / curative labeling claim for a
one-time cell or gene therapy for a qualified Regulatory Affairs + Medical Affairs
reviewer. You have no stake in the outcome. Assess whether the claim is supported
by the long-term follow-up data, grounded only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

Product description: {product_description}
Proposed claim: {proposed_claim}
Pivotal efficacy summary: {pivotal_efficacy_summary}
Follow-up duration and n: {followup_duration_and_n}
Durability evidence: {durability_evidence}
Population and endpoint: {population_and_endpoint}
Comparator / natural history: {comparator_or_natural_history}
Label context: {label_context}

Produce a structured review with exactly these sections:

## Durability vs follow-up
State whether the durability claim stays within the observed follow-up and
censoring; identify any claim beyond the data.

## Follow-up evidence
State whether n, median follow-up, and loss-of-response support the claimed
persistence of effect.

## Curative language
State whether any curative / permanent-benefit language is supported by the
endpoint.

## Comparator / natural-history context
State whether the claim is contextualised against a comparator or natural history.

## Claim conclusion
State whether the durability / curative claim is supported, or whether it
overstates benefit.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
