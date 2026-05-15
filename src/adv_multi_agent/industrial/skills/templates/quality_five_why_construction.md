---
name: quality_five_why_construction
description: Construct a 5-Why causal chain from a quality incident's evidence inventory to a true root cause
inputs: [incident_summary, evidence_inventory, initial_causal_hypothesis]
---
You are a quality engineer running an 8D / DMAIC investigation. Construct the 5-Why with evidence anchors.

Incident summary: {incident_summary}
Evidence inventory: {evidence_inventory}
Initial hypothesis: {initial_causal_hypothesis}

For each Why-step:
1. State the why-question.
2. State the cause hypothesis.
3. Cite the supporting evidence (SPC, MSA, teardown, traceability) — quantitative if available.
4. State the falsification test (what evidence would refute this cause).
5. If "operator error" surfaces, ask: was the process operator-proofed? Was the operator-proof control tested?

Continue until a true root cause is reached (one whose elimination prevents recurrence).

Output:
- 5-Why chain with evidence and falsification test per step
- Identified root cause(s)
- Operator-error claim integrity: [Supported by evidence / Convenient attribution]
- Open evidence gaps (what would solidify the chain)
