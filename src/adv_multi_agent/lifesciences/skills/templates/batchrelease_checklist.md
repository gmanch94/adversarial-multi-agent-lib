---
name: batchrelease_checklist
description: Pre-sign-off checklist for the Qualified Person to clear before a batch-release disposition is executed
inputs:
  - flags
---

Owner: Qualified Person / Quality Release.

Before the disposition is executed:
- [ ] Re-classify the deviation criticality against its CQA/safety impact
- [ ] Identify every affected CQA in the impact assessment
- [ ] Establish the root cause and link an adequate CAPA
- [ ] Confirm no batch is released except by the QP through the controlled release register
- [ ] Obtain Qualified Person sign-off before the disposition is executed

If a REVIEWER VETO is present: a 'release' disposition is proposed for a batch
with an unresolved critical deviation. Do not release; escalate to the QP until
the deviation is resolved.

Outstanding flags:
- {flags}
