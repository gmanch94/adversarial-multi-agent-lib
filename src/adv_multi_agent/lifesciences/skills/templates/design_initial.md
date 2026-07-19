---
name: design_initial
description: Initial draft of a design-control traceability audit; maps every design input->output->verification->validation link against the DHF evidence
inputs:
  - request_text
  - wiki_context
---

You are auditing design-control traceability for a Design Assurance engineer to
review. You have no stake in the outcome. Audit input->output->verification->
validation links against the supplied Design History File evidence — not against
general device norms.

BASE EVERY FINDING ON THE INPUT EVIDENCE. Do not assert a trace link that is not
present in the design inputs, design outputs, verification, or validation
evidence below.

DESIGN HISTORY FILE EXCERPT (caller-supplied — verify against the PLM/eQMS
before acting):
{request_text}

{wiki_context}

Produce an audit with:

## Traceability matrix summary
- Input-to-output and output-to-input link status; name every orphan

## Verification coverage
- Each design output and its cited verification evidence (or the gap)

## Validation coverage
- Each user need and its cited design-validation evidence (or the gap)

## Risk-control linkage
- ISO 14971 risk controls and the V&V that confirms their effectiveness

## Gaps and recommendations
- Specific, closeable gaps (which input, which output, what evidence)

## Claims
- Specific factual claims about the DHF evidence that ground the audit
