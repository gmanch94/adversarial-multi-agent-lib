---
name: gxp_checklist
description: Pre-sign-off checklist for QA / Data Integrity to clear before batch or record disposition
inputs:
  - flags
---

Owner: Quality Assurance / Data Integrity Lead.

Before any batch or record disposition:
- [ ] Confirm every finding resolves against the controlled source systems (LIMS / MES / historian / CDS), not the caller summary
- [ ] Open or link a CAPA for each unresolved data-integrity finding
- [ ] Escalate systemic findings to the data-governance council
- [ ] Obtain QA / Data Integrity sign-off before disposition

Outstanding flags:
- {flags}
