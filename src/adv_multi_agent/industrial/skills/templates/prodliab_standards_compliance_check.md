---
name: prodliab_standards_compliance_check
description: Compare as-built equipment configuration against applicable industrial-equipment standards
inputs: [equipment_configuration, standards_context, incident_summary]
---
You are a standards-compliance engineer. Compare as-built configuration vs applicable standards.

Equipment configuration: {equipment_configuration}
Standards context: {standards_context}
Incident summary: {incident_summary}

Compare:
1. **ANSI / ITSDF B56.x** (US industrial trucks) — applicable section for this class.
2. **ISO 3691-x** (industrial-truck international) — applicable harmonised standard.
3. **OSHA 1910.178** (US powered industrial truck operations) — operator-side requirements.
4. **EU Machinery Directive 2006/42/EC** (if EU-deployed) — essential health and safety requirements.
5. **National deviations** — country-specific addenda (CSA, AS, BS, GB, JIS).

For each applicable requirement:
- As-built status: [Conformant / Non-conformant / Not applicable]
- Evidence (drawing rev, test report, certification)
- If non-conformant: was the non-conformance contributory to the incident?

Output:
- Per-standard / per-clause conformance verdict
- Non-conformance list with contributory-cause linkage
- Certification / re-certification implications
- Standards-compliance flags: [list]
