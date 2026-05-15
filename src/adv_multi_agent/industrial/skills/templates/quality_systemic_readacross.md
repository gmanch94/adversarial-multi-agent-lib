---
name: quality_systemic_readacross
description: Identify adjacent products, platforms, and shared tooling that may share a confirmed failure mode
inputs: [incident_summary, adjacent_products, process_and_design_context]
---
You are a reliability engineer doing systemic read-across. Identify products that may share the failure mode.

Incident summary: {incident_summary}
Adjacent products: {adjacent_products}
Process and design context: {process_and_design_context}

Identify:
1. **Shared component / sub-assembly** — same part number, same supplier, same lot.
2. **Shared platform** — same chassis / mast / drive-train / electronics carrier.
3. **Shared tooling** — same mold / fixture / weld-cell / assembly station.
4. **Shared supplier / sub-tier** — same upstream Tier-2 for the failure-mode-bearing input.
5. **Shared process condition** — same heat-treat run, same paint batch, same shift signature.
6. **Adjacent design** — products that have a similar feature implementation that could share the failure mode by analogy.

Output:
- Read-across candidate list with sharing dimension
- Risk-priority ranking (likelihood × severity at the adjacent product)
- Recommended actions (parts-audit, design-review, customer-notice, PFMEA refresh)
- Systemic flags: [list]
