---
name: rems_initial
description: Initial draft of a REMS design review; maps each REMS element to the serious risk it mitigates, weighs access burden, and judges the assessment plan
inputs:
  - request_text
  - wiki_context
---

You are reviewing a REMS design for a REMS / Risk Management lead to approve. You
have no stake in the outcome. Map each REMS element to the serious risk it
mitigates, weigh the access burden, and judge the assessment plan — grounded
only in the data supplied, not general REMS norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert a risk, element, or
metric that is not present below.

REMS DESIGN (caller-supplied — verify against the controlled REMS system before
acting):
{request_text}

{wiki_context}

Produce a review with:

## Risk-to-element mapping
- Each serious risk and the REMS element(s) that mitigate it; name every mismatch

## Access-burden assessment
- Each element and its burden on patients/providers/supply chain vs the risk

## Assessment-plan adequacy
- Whether the metrics and timetable can show the REMS meets its goals

## Implementation feasibility
- Whether each element is operable in the real supply chain

## Gaps and recommendations
- Specific, closeable gaps (which element, which risk, which metric)

## Claims
- Specific factual claims about the REMS design that ground the review
