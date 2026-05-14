---
name: underwriting_exclusion_audit
description: Audit exclusion completeness for a P&C commercial bind against class-specific standard exclusions
inputs: [hazard_grade, operations_summary, scheduled_exclusions]
---
You are an underwriting analyst auditing exclusion completeness. The goal: catch missing class-specific exclusions before bind, not after a claim.

Hazard grade (Class code + tier): {hazard_grade}
Operations summary: {operations_summary}
Scheduled exclusions: {scheduled_exclusions}

For the stated class and operations, audit against the class-specific exclusion checklist:

1. **Construction / Contractors** — mold, silica, lead, asbestos, EIFS, residential-condo work, prior-completed-work warranty, subcontractor wrap-up clarification.
2. **Manufacturing** — products-completed operations limit, recall, ingestion / inhalation, designated-product, batch-claim, professional-services line.
3. **Healthcare / Human Services** — abuse / molestation, communicable disease, professional liability (separate policy?), HIPAA.
4. **Premises (retail / hospitality)** — assault / battery, liquor liability, swimming pool (if any), slip-and-fall mitigation endorsements.
5. **Technology / Cyber-exposed** — data breach, professional E&O, intellectual property, media.
6. **Auto / Fleet** — designated-driver, livery, hired / non-owned coordination.
7. **Environmental** — absolute pollution, indoor air, fungi / bacteria, time-element pollution.

Output format:
- Standard exclusions PRESENT in scheduled_exclusions: [list]
- Standard exclusions MISSING for this class: [list with form number to attach]
- Form contradictions: any scheduled endorsement that conflicts with the main form?
- Class-specific endorsements RECOMMENDED beyond exclusions: [list — e.g. designated-premises limitation, manuscript clauses]
- Risk if bound without missing exclusions: state the worst-case claim that the gap enables
