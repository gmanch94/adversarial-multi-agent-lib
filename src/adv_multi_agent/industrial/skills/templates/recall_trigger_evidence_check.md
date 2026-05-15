---
name: recall_trigger_evidence_check
description: Evaluate trigger evidence for a CPSC substantial-product-hazard analysis
inputs: [trigger_summary, evidence_inventory]
---
You are a product-safety analyst preparing CPSC § 15(b) substantial-product-hazard analysis.

Trigger summary: {trigger_summary}
Evidence inventory: {evidence_inventory}

Evaluate against the four CPSC § 15(b) tiers:
1. **Death or serious injury** — has death or serious injury occurred or is the risk evident?
2. **Unreasonable risk** — could a reasonable consumer / operator be unreasonably exposed?
3. **Standard non-compliance** — does the product fail a mandatory safety standard?
4. **Pattern of defect** — does the field-failure population show a defect pattern?

For each tier, cite the evidence (field-failure count, severity distribution, witness reports, regulator inquiry).

Verdict:
- SPH tier: [Tier 1 / Tier 2 / Tier 3 / Tier 4 / Not SPH]
- "Becomes aware" trigger date (CPSC § 15(b) 5-business-day clock)
- Evidence sufficiency: [Strong / Moderate / Anecdotal]
- Trigger-evidence flags: [list]
