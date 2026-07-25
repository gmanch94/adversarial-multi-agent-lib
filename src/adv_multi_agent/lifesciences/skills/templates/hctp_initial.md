---
name: hctp_initial
description: Initial HCT/P regulatory-tier classification; applies all four 21 CFR 1271.10(a) prongs (minimal manipulation, homologous use, combination, systemic effect) against the supplied data
inputs:
  - product_description
  - cellular_tissue_source
  - manufacturing_steps
  - minimal_manipulation_rationale
  - intended_use_homology
  - combination_with_another_article
  - systemic_effect_or_metabolic_dependence
  - proposed_regulatory_tier
  - precedent_determinations
---
You are classifying a human cell/tissue product as a 361 HCT/P (no premarket
approval) or a 351 biologic (requires a BLA) for a qualified Regulatory Affairs
lead. You have no stake in the outcome. Apply ALL FOUR 21 CFR 1271.10(a) prongs —
minimal manipulation, homologous use, not-combined-with-another-article, and no
systemic effect / no dependence on metabolic activity — grounded only in the data
supplied.

BASE THE REVIEW ON THE INPUT DATA ONLY.

Product description: {product_description}
Cellular / tissue source: {cellular_tissue_source}
Manufacturing steps: {manufacturing_steps}
Minimal-manipulation rationale: {minimal_manipulation_rationale}
Intended use / homology: {intended_use_homology}
Combination with another article: {combination_with_another_article}
Systemic effect / metabolic dependence: {systemic_effect_or_metabolic_dependence}
Proposed regulatory tier: {proposed_regulatory_tier}
Precedent determinations: {precedent_determinations}

Produce a structured classification with exactly these sections:

## Minimal manipulation (prong 1)
State whether processing keeps the product minimally manipulated; identify any
step that alters the relevant biological characteristics.

## Homologous use (prong 2)
State whether the intended use is homologous to the tissue's original basic
function; identify any non-homologous use.

## Combination and systemic effect (prongs 3 and 4)
State whether the product is combined with another article (beyond the allowed
exceptions) and whether it has a systemic effect or depends on the metabolic
activity of living cells.

## Tier conclusion
State whether the product is a 361 HCT/P or a 351 biologic, following from all
four prongs.

## Precedent
State whether the tier is consistent with cited regulatory precedent.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
