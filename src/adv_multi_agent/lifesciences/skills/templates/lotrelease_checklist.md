---
name: lotrelease_checklist
description: QC / Quality Engineering sign-off checklist for a CGT lot-release specification audit; includes outstanding SPEC-COVERAGE, SMALL-LOT, and SHELF-LIFE flags
inputs:
  - spec_coverage_flags
  - small_lot_flags
  - shelf_life_flags
  - product_description
---

[OWNER: Quality Control / Quality Engineering]

Before the lot-release specification set supports disposition of: {product_description}
- [ ] Confirm every release-critical attribute has a validated method + acceptance criterion
- [ ] Confirm the sampling / test-consumption plan is practical for the lot size
- [ ] Confirm the short-shelf-life rapid / real-time-release strategy is validated and justified
- [ ] Obtain QC / Quality Engineering sign-off before lot disposition

Outstanding flags:
- Spec-coverage: {spec_coverage_flags}
- Small-lot: {small_lot_flags}
- Shelf-life: {shelf_life_flags}
