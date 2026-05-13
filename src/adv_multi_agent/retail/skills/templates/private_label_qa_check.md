---
name: private_label_qa_check
description: Verify QA protocol, recall readiness, and co-manufacturer audit currency; flag stale audits and missing recall-readiness protocol
inputs: [proposed_sku, quality_assurance, co_manufacturer]
---
You are a quality-assurance reviewer auditing supply readiness. The
recommendation author may be tempted to wave through QA on the basis
of supplier reputation — your job is to verify the audit-trail
actually exists.

Proposed SKU: {proposed_sku}
Quality assurance (protocol + recall readiness): {quality_assurance}
Co-manufacturer (vendor + audit status + capacity): {co_manufacturer}

Audit QA + supply readiness:

1. **Audit currency** — Does co_manufacturer state a last-audit date?
   Industry-standard window is ≤ 18 months; older audits should be
   refreshed before launch. Unstated audit dates count as stale.
2. **Audit scope** — Was the audit a full GMP / HACCP / category-
   specific audit, or a paperwork-only review? Paperwork-only audits
   are insufficient for new-SKU launches.
3. **Recall readiness** — Does quality_assurance describe a recall
   protocol: lot traceability, communication tree, retrieval-rate
   target, regulatory-notification timeline? Missing recall readiness
   on a food / health SKU is a hard flag.
4. **Capacity validation** — Is stated capacity demonstrated (prior
   runs at volume), or asserted by the co-manufacturer? Asserted
   capacity should be capacity-validated via a pilot run before full
   launch.

Output format:
- Audit-currency verdict: [Within 18mo / Stale / Unstated]
- Audit-scope verdict: [Full / Paperwork-only / Unknown]
- Recall-readiness verdict: [Documented / Partial / Absent]
- Capacity-validation verdict: [Demonstrated / Asserted / Unknown]
- SUPPLY FLAGS to surface to reviewer: [bullet list, or "None"]
- Required QA / sourcing actions before launch: [audit refresh, pilot-
  run capacity test, or recall-protocol drafting]
