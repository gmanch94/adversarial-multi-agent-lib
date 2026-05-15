---
name: recall_regulatory_notification_map
description: Map regulator notifications required for an industrial-equipment recall across applicable jurisdictions
inputs: [trigger_summary, regulatory_context, fleet_serial_traceability]
---
You are a regulatory-counsel partner. Map the recall notification obligations.

Trigger summary: {trigger_summary}
Regulatory context: {regulatory_context}
Fleet serial traceability: {fleet_serial_traceability}

Map per jurisdiction:
1. **US — CPSC § 15(b)** — substantial-product-hazard report; 5-business-day clock; reporting form.
2. **US — OSHA** — workplace-incident notification if employer reports; recordable / non-recordable.
3. **US — NHTSA-equivalent** — N/A for off-road industrial trucks; applicable if road-going.
4. **EU — Safety Gate (RAPEX)** — Article 5 GPSR notification; PROSAFE network.
5. **EU — Machinery Directive notification** — to market-surveillance authority of each member state where deployed.
6. **State AG** — California Prop 65 / state-specific consumer-protection if applicable.
7. **Country-specific** — Canada (CCPSA), Australia (ACL), Japan (METI), GB / China (AQSIQ).

For each applicable jurisdiction:
- Reporting clock (24-hr / 5-business-day / immediate / 30-day)
- Form / portal
- Addressee
- Content requirements

Output:
- Notification matrix (jurisdiction × clock × form × addressee)
- Regulatory-notify flags: [list of missed or late-clock jurisdictions]
