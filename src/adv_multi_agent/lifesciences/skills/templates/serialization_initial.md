---
name: serialization_initial
description: Initial draft of a serialization / DSCSA traceability review; assesses aggregation integrity, EPCIS/traceability event coverage, and saleable-return verification
inputs:
  - request_text
  - wiki_context
---

You are reviewing a serialization / DSCSA traceability configuration for a
Supply-Chain Compliance lead to approve. You have no stake in the outcome. Assess
the aggregation integrity, the EPCIS/traceability event coverage, and the
saleable-return verification — grounded only in the data supplied.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert an aggregation link,
event, or return that is not present below.

SERIALIZATION / DSCSA DATA (caller-supplied — verify against the controlled
serialization/EPCIS systems before acting):
{request_text}

{wiki_context}

Produce a review with:

## Aggregation integrity
- Each packaging tier and its parent-child link status; name every broken link

## Traceability event coverage
- Each required EPCIS event / trading-partner element and whether it is present

## Saleable-return verification
- Whether each saleable return is verified at the unit level before resale

## Interoperability readiness
- Whether the system supports enhanced unit-level traceability and exchange

## Gaps and recommendations
- Specific, closeable gaps (which tier, which event, which return)

## Claims
- Specific factual claims about the serialization configuration that ground the review
