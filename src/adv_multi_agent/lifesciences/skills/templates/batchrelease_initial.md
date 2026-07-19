---
name: batchrelease_initial
description: Initial draft of a batch-release deviation disposition; classifies criticality, assesses CQA impact, judges release risk, recommends disposition
inputs:
  - request_text
  - wiki_context
---

You are producing a batch-release deviation disposition for a qualified
Qualified Person / Quality Release approver. You have no stake in the outcome.
Your job is to classify the deviation criticality, assess CQA/safety impact,
judge the release risk, and recommend a disposition — grounded only in the data
supplied.

BASE THE DISPOSITION ON THE INPUT DATA ONLY.

BATCH-DEVIATION DATA:
{request_text}

{wiki_context}

Produce a structured disposition with exactly these sections:

## Deviation summary
Summarise the deviation, the batch, and the manufacturing step from the input.

## Criticality classification
Classify the deviation (minor / major / critical) against its CQA and patient-
safety impact. Do not under-classify a deviation that affects a CQA.

## Impact assessment
Identify every affected critical quality attribute and the impact on product
quality and safety.

## Release-risk judgment
State whether the proposed disposition leaves unresolved risk to the patient or
the CQA.

## Root cause, CAPA, and disposition
State the root cause, the linked CAPA, and the recommended disposition (release /
reject / rework).

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
