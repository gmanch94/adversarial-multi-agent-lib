---
name: durability_checklist
description: Regulatory Affairs + Medical Affairs sign-off checklist for a CGT durability / curative claim review; includes outstanding flags and veto do-not-make-claim row
inputs:
  - veto_reason
  - durability_claim_flags
  - followup_evidence_flags
  - curative_language_flags
  - product_description
---

[OWNER: Regulatory Affairs + Medical Affairs]

Before any durability / curative claim is made for: {product_description}
- [ ] If REVIEWER VETO issued — do not make the durability / curative claim; escalate to Regulatory Affairs + Medical Affairs and narrow the claim to the supported follow-up window. Veto directive: {veto_reason}
- [ ] Confirm the durability claim stays within the observed follow-up
- [ ] Confirm follow-up n and duration support persistence of effect
- [ ] Confirm curative language is supported by the endpoint
- [ ] Obtain Regulatory Affairs + Medical Affairs sign-off before any use

Outstanding flags:
- Durability-claim: {durability_claim_flags}
- Followup-evidence: {followup_evidence_flags}
- Curative-language: {curative_language_flags}
