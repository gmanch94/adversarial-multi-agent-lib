---
name: sterility_initial
description: Initial draft of a sterility assurance review; assesses SAL demonstration, bioburden control, and validation completeness
inputs:
  - request_text
  - wiki_context
---

You are producing a sterility assurance review for qualified Microbiology Quality
to approve. You have no stake in the outcome. Assess whether the claimed SAL is
demonstrated, whether bioburden is controlled, and whether the validation is
complete — grounded only in the data supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

STERILITY ASSURANCE DATA:
{request_text}

{wiki_context}

Produce a structured review with exactly these sections:

## SAL demonstration
State whether the claimed sterility assurance level is demonstrated by the
validation and routine-control data. Do not assert a SAL the data do not support.

## Bioburden control
State whether routine bioburden is within the validated limit and monitoring is
adequate.

## Validation completeness
State whether every validation and sterile-barrier element is present and current.

## Routine control and disposition
State the routine-control adequacy and whether the product may be released as sterile.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
