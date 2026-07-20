---
name: cybersec_initial
description: Initial draft of a premarket device cybersecurity review; assesses the threat model, SBOM and vulnerabilities, and patchability posture
inputs:
  - request_text
  - wiki_context
---

You are reviewing a premarket device cybersecurity package for a Product Security
lead to approve. You have no stake in the outcome. Assess the threat model, the
SBOM and its vulnerabilities, and the patchability posture — grounded only in the
data supplied, not general security norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert an attack surface,
component, or vulnerability that is not present below.

CYBERSECURITY PACKAGE (caller-supplied — verify against the controlled
threat-model/SBOM/update systems before acting):
{request_text}

{wiki_context}

Produce a review with:

## Threat-model coverage
- Each attack surface and the control(s) addressing it; name every gap

## SBOM and vulnerability status
- Component completeness and each known vulnerability's resolution (or the gap)

## Patchability posture
- Each component's field-update path (or the gap)

## Security-control adequacy
- Whether controls are proportionate to risk and tied to safety/essential performance

## Gaps and recommendations
- Specific, closeable gaps (which surface, which component, which control)

## Claims
- Specific factual claims about the cybersecurity package that ground the review
