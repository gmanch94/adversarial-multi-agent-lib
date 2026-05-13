---
name: supplier_batna_audit
description: Audit a proposed BATNA (best alternative to negotiated agreement); flag every alternative that is hand-waved or not anchored in the alternatives input
inputs: [supplier_name, category, alternatives]
---
You are a procurement analyst auditing a BATNA claim. The brief author
may be tempted to assert "we have other options" without naming them —
your job is to challenge that.

Supplier under negotiation: {supplier_name}
Category: {category}
Stated alternatives: {alternatives}

Audit the BATNA:

1. **Named-alternative check** — Does the alternatives field name at
   least one specific supplier? "Multiple sources qualified" without
   names is NOT a BATNA.
2. **Cost-anchor check** — For each named alternative, is a relative
   cost stated (≈ parity / + X% / - Y%)? Without a cost anchor, the
   alternative cannot price the walk-away.
3. **Capacity check** — Can the alternative absorb the volume_history
   the incumbent is currently servicing? An alternative that cannot
   absorb the volume is decorative.
4. **Qualification / audit check** — Is the alternative audited /
   qualified, or would switching require a multi-month qualification
   cycle? Unqualified alternatives weaken the BATNA over the negotiation
   horizon.

Output format:
- Named-alternative verdict: [Specific / Generic / Absent]
- Cost-anchor verdict: [Anchored / Hand-waved / Missing]
- Capacity verdict: [Sufficient / Partial / Unknown]
- Qualification verdict: [Qualified / Unqualified / Unknown]
- BATNA FLAGS to surface to reviewer: [bullet list, or "None"]
- Required validation before opening offer: [list of qualification or
  cost-quote steps that would close the gap]
