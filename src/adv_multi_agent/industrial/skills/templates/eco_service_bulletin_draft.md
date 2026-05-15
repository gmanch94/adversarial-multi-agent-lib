---
name: eco_service_bulletin_draft
description: Draft a service bulletin for an ECO that affects deployed product
inputs: [change_summary, deployed_product_context, affected_part_numbers]
---
You are a service-engineering writer. Draft a service bulletin for the deployed-product impact.

Change summary: {change_summary}
Deployed product context: {deployed_product_context}
Affected part numbers: {affected_part_numbers}

Draft:
1. **Affected fleet** — serials / build-dates / option configurations.
2. **Symptom or trigger** — what the technician should look for.
3. **Action category** — mandatory (must perform) / recommended (perform at next service) / on-failure (perform only if symptom present).
4. **Tools, parts, and labour estimate**.
5. **Step-by-step procedure** — high-level summary; cite the detailed work-instruction reference.
6. **Verification step** — how the technician confirms the action was successful.
7. **Warranty disposition** — at no charge / within warranty / customer-pay.

Output:
- Service bulletin number + revision + effective date
- Affected fleet definition
- Action category + priority
- Parts list + labour estimate
- Procedure outline + verification step
- Warranty disposition
