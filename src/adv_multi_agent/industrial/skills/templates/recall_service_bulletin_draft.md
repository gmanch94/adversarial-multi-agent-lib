---
name: recall_service_bulletin_draft
description: Draft a recall service bulletin / safety bulletin for an industrial-equipment recall action
inputs: [trigger_summary, fleet_serial_traceability, service_capacity_context]
---
You are a service-engineering writer. Draft the recall service bulletin.

Trigger summary: {trigger_summary}
Fleet serial traceability: {fleet_serial_traceability}
Service capacity context: {service_capacity_context}

Draft:
1. **Safety bulletin number + effective date + revision**.
2. **Affected serials / build dates / configurations / regions**.
3. **Hazard description** — plain language; what could happen; severity tier.
4. **Operator action until repair** — stop use / continue with restrictions / no restriction.
5. **Repair action** — parts replaced, software updated, re-inspection.
6. **Parts list + tools + estimated labour** — verify against parts catalog + DC inventory + service-network reach.
7. **Customer contact** — how the customer schedules the action; who pays.
8. **Verification step** — how the technician confirms the action is complete.
9. **Reporting back** — how the field-fix completion data flows to the OEM tracking system.

Output:
- Service bulletin draft text
- Parts availability verdict (Sufficient / Tight / Inadequate)
- Service-network capacity verdict
- Customer-communication plan
