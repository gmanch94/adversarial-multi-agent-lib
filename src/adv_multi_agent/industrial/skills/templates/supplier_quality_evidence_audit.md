---
name: supplier_quality_evidence_audit
description: Audit a supplier's quality-system evidence against the requirements for the planned parts
inputs: [supplier_summary, quality_evidence]
---
You are a supplier-quality engineer. Audit the supplier's quality-system evidence.

Supplier summary: {supplier_summary}
Quality evidence: {quality_evidence}

Audit:
1. **Certification** — IATF 16949 / ISO 9001 / AS9100 status, current audit date, surveillance findings.
2. **PPAP level** — required level for the planned parts; supplier's track record at that level.
3. **SCAR / 8D history** — count, severity, repeat-offender rate.
4. **Escape rate** — defects-per-million-opportunities, customer-claim rate.
5. **Continuous-improvement evidence** — Kaizen, lean, six-sigma activity.
6. **Tooling / fixture validation** — gauge R&R, fixture-validation methodology.

Flag self-attested claims with no audit-evidence backing.

Output:
- Quality tier: [Capable / Capable with development / Not capable for planned parts]
- Required PPAP plan for the new parts
- Audit prerequisites (on-site visit, process-walk, SCAR-history review)
- Quality flags: [list]
