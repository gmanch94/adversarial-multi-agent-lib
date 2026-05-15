---
name: prodliab_operator_error_integrity
description: Audit the integrity of an operator-error attribution for a product-liability incident
inputs: [incident_summary, telematics_and_trace, operator_and_training]
---
You are a product-safety engineer. Audit whether the operator-error attribution is supported by evidence.

Incident summary: {incident_summary}
Telematics and trace: {telematics_and_trace}
Operator and training: {operator_and_training}

Audit:
1. **Telematics / video / EDR** — does the trace show operator input consistent with the claimed action?
2. **Training-of-record** — was the operator trained on the task they were performing?
3. **Manual / placard / warning** — does the operator manual address this action? Was the placard present and legible?
4. **Foreseeability** — was the operator's action foreseeable misuse the design should tolerate?
5. **Engineering-controls test** — was there an engineering control (interlock, geofence, speed-limit) that should have prevented the action? Was it operational?

Verdict:
- Operator-error attribution: [Supported by evidence / Plausible but unproven / Convenient — design or warning gap masked]
- Telematics evidence sufficiency: [Strong / Moderate / Insufficient]
- Operator-training adequacy: [Adequate / Gap / Not applicable]
- Operator-error flags: [list]
