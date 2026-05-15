---
name: quality_containment_scope_check
description: Check containment scope and sort method for a quality incident
inputs: [incident_summary, containment_scope, process_and_design_context]
---
You are a quality engineer reviewing containment. Check the scope and the sort method.

Incident summary: {incident_summary}
Containment scope: {containment_scope}
Process and design context: {process_and_design_context}

Check:
1. **Scope coverage** — in-plant WIP, finished goods at plant, in-transit to DC, DC stock, in-transit to customer, customer-held, in-service / field-deployed.
2. **Date / lot / serial bounding** — is the affected band correctly identified at each scope layer?
3. **Sort method** — 100% inspection / Cpk-bounded sampling / engineering screen / no sort possible.
4. **Measurement-system capability** — is the sort method's gauge/method capable of discriminating defective vs conforming for this defect mode?
5. **Effectiveness verification** — how does the team confirm containment worked (escape-rate post-sort)?

Output:
- Scope coverage matrix (each layer × covered / not covered / not applicable)
- Sort-method assessment per layer
- Measurement-system capability verdict
- Recommended scope expansions
- Containment flags: [list]
