---
name: comparability_checklist
description: Regulatory Affairs + CMC sign-off checklist for a CGT post-change comparability review; includes outstanding flags and veto do-not-treat-as-comparable row
inputs:
  - veto_reason
  - process_delta_flags
  - analytical_gap_flags
  - clinical_bridge_flags
  - product_description
---

[OWNER: Regulatory Affairs + CMC Lead]

Before implementing the manufacturing change for: {product_description}
- [ ] If REVIEWER VETO issued — do not treat the product as comparable; escalate to Regulatory Affairs + CMC and generate the required new clinical data before implementing the change. Veto directive: {veto_reason}
- [ ] Confirm every critical quality attribute affected by the change is covered
- [ ] Confirm the analytical panel supports the comparability conclusion
- [ ] Confirm residual uncertainty is bridged clinically or new data are planned
- [ ] Obtain Regulatory Affairs + CMC sign-off before implementing the change

Outstanding flags:
- Process-delta: {process_delta_flags}
- Analytical-gap: {analytical_gap_flags}
- Clinical-bridge: {clinical_bridge_flags}
