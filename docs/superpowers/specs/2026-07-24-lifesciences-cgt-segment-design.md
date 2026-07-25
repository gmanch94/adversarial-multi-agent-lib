# Lifesciences — Cell & Gene Therapy (CGT/ATMP) Segment — Design Doc

**Date:** 2026-07-24
**Status:** DESIGN APPROVED — MVP-8 approved; 4 Phase-2 designs locked; implementation pending
**Lineage:** 5th segment of the `lifesciences` domain (7th domain). Inherits the locked no-base-class recipe (D-RETAIL-7 → D-IND-1 → D-HEALTH-1 → D-LIFESCI-1). Extends [`2026-07-19-lifesciences-domain-design.md`](2026-07-19-lifesciences-domain-design.md).

---

## Why CGT/ATMP fits the ARIS pattern (and why it is the sharpest case yet)

Cell & gene therapy is the most acute instance of the domain's core failure mode — **motivated under-classification** — because the cheaper regulatory call is worth the most here. A sponsor that can argue its product is a "361 HCT/P" (minimal manipulation + homologous use) skips the entire BLA. A sponsor whose potency assay "supports" lot release ships a living product on an activity claim the assay does not actually measure. A sponsor whose post-change product is "comparable" avoids repeating a clinical study that costs years. In every cell, a knowledgeable author can confabulate a plausible CBER-flavored rationale for the answer the business wants, and a single-model author has no counter-incentive.

A cross-model reviewer with no stake in the submission is positioned to catch exactly this: a 351 biologic dressed as a 361 HCT/P, a potency claim the assay's mechanism-of-action linkage cannot bear, an ineligible-donor release, a curative claim the follow-up duration cannot support. The five halt-worthy CGT calls map cleanly onto the reviewer-veto pattern — a fundamentally-unsupportable output should be **stopped**, not merely flagged, because the downstream act (release a lot, file a BLA-avoidance position, make a cure claim) is hard to reverse and patient-facing.

This is still the manufacturer's regulatory-affairs / quality desk — a biopharma/advanced-therapy **manufacturer**, not the treating clinic and not the general factory floor.

## Segment identity + boundary

CGT/ATMP is the **5th product segment** of the same diversified-manufacturer archetype (joining diagnostics · devices · pharma · nutrition). The intended user is a regulatory-affairs specialist, CMC/analytical lead, quality engineer, tissue-safety officer, or biosafety reviewer at an advanced-therapy manufacturer.

FDA **CBER-primary** framing (21 CFR 1271 HCT/P regulation, the 600-series biologics regulations, the BLA pathway, CBER expedited programs). The EMA **ATMP** regime (Regulation 1394/2007, EMA CAT) is noted as a *parallel* in module docstrings and reviewer criteria — it is **not** a separate set of EU workflows (that would be the geography axis, out of scope for this segment).

Boundary vs the already-shipped lifesciences workflows (stated in each new module's docstring; no shared code, distinct decision):

| New CGT workflow | Adjacent shipped workflow | Distinction |
|------------------|---------------------------|-------------|
| `CGTPotencyAssayWorkflow` (#2) | `AssayPerformanceClaimWorkflow` | Therapeutic MoA-linked biological-activity **lot-release** assay for a living product — not an in-vitro-diagnostic analytical/clinical performance claim. |
| `CGTComparabilityWorkflow` (#3) | `BiosimilarComparabilityWorkflow` | Living cell / viral-vector product, small patient-specific autologous lots — not a well-characterized recombinant-protein analytical-similarity exercise. |
| `CGTDurabilityClaimWorkflow` (#5) | `PromotionalOffLabelReviewWorkflow` | Pre-approval clinical/labeling claim substantiated against long-term follow-up data — not MLR review of marketing copy against an already-approved label. |
| `DonorEligibilityWorkflow` (#4) | healthcare `AdverseEventTriageWorkflow` | Manufacturer's 21 CFR 1271 Subpart C regulatory **eligibility determination** — not clinical patient care. |
| Phase-2 `ViralVectorSheddingWorkflow` / CGT sterility scope | `SterilityAssuranceWorkflow` | Short-shelf-life real-time / rapid-method release for a non-terminally-sterilized living product — not terminal-sterilization / aseptic SAL for a conventional device or drug. |

## Segment decisions (extend D-LIFESCI-*)

| # | Decision |
|---|----------|
| D-LIFESCI-5 | 5th lifesciences segment = advanced therapies (cell & gene / ATMP). FDA **CBER-primary** (21 CFR 1271, 600-series, BLA, expedited programs); EMA ATMP (Reg 1394/2007) is a docstring/criteria **parallel only**, not a separate EU workflow set. MVP-8 cut + 4 Phase-2 designs locked here for fill-in-not-redesign. Same no-domain-base-class rule (D-IND-1 / D-RETAIL-7 lineage). |
| D-LIFESCI-6 | Reviewer-veto on the 5 halt-worthy CGT regulatory-integrity workflows (#1 HCT/P classification, #2 potency, #3 comparability, #4 donor-eligibility, #5 durability-claim); no-veto on the 3 advisory-analysis workflows (#6 RMAT, #7 vector-safety, #8 lot-release-spec). Same split logic as D-LIFESCI-4. |
| D-LIFESCI-3 (extended) | The no-brand rule is unchanged and now also guards CGT: the tripwire denylist (`tests/unit/test_lifesciences_no_brand_names.py`) gains **base64-encoded seeds for currently-approved CAR-T / gene-therapy product trade names and common cell-processing platform / instrument brand names**. No plaintext brand string enters any artifact (code, prompt, example, test, or this spec). Scenarios use generic categories only: "an autologous CAR-T", "an AAV-vectored gene therapy", "an allogeneic iPSC-derived cell therapy", "a lentiviral ex-vivo gene-modified product". |

## Convention inheritance (verbatim, not re-solved)

All 12 lifesciences conventions apply unchanged (see the domain design doc §"Convention recap"). Key load-bearing points for this segment:

- `*Request` dataclass with `to_prompt_text()`; every free-text field capped at `_MAX_FIELD_CHARS = 1500`; `sanitize_for_prompt` at the boundary (6000-char post-concat cap).
- Convergence = `review.approved AND not current_flags AND not veto` via `self._flag_classes_unresolved(...)` — **never** a bare `not any(...)` (D-A11-1). Every `_FLAG_HEADERS` member also appears in that module's reviewer-criteria emission block (G5 contract).
- `extract_flags` / `truncate_flag_display` / `extract_veto_directive` shared helpers (inherits M1 line-anchor + H-IND-1 sibling-stop + L-PC-5 display cap + M-PC-1 veto-marker anchor).
- Veto output composes `{_VETO_BANNER}\n\nVETO DIRECTIVE: {veto_reason}\n\n--- Vetoed draft below ---\n\n{draft}\n\n---\n\n{_DISCLAIMER}` (D-DEPTH-2); metadata scalars via `sanitize_for_prompt(..., max_chars=200)` (L-HEALTH-2).
- `_DISCLAIMER` injected in code (convention #10), not from prompt; approver role printed as the checklist's first line.
- Block-form template frontmatter (post-`c1a7414` registry fix) so all 8 templates are discoverable.

**Flag-header safety (H-IND-1) — verified for all 24 MVP-8 headers + 12 Phase-2 hint headers:** every header is uppercase **letters + spaces + hyphens only**. Zero digit-, slash-, or paren-containing headers. The shared `_is_sibling_header_lhs` regex covers all of them; **no `core/_internal.py` change required.** Numeric regulatory tokens (361, 351, 1271, 803) appear only in prose, field names, and criteria — **never** as a flag header.

## Package structure (additive only)

```
src/adv_multi_agent/lifesciences/workflows/
  hctp_classification.py            # HCTPClassificationWorkflow            [veto]
  cgt_potency_assay.py              # CGTPotencyAssayWorkflow               [veto]
  cgt_comparability.py              # CGTComparabilityWorkflow              [veto]
  donor_eligibility.py              # DonorEligibilityWorkflow              [veto]
  cgt_durability_claim.py           # CGTDurabilityClaimWorkflow            [veto]
  rmat_designation.py               # RMATDesignationWorkflow               [no veto]
  vector_safety.py                  # VectorSafetyWorkflow                  [no veto]
  cgt_lot_release_spec.py           # CGTLotReleaseSpecWorkflow             [no veto]
src/adv_multi_agent/lifesciences/skills/templates/   # +8 templates (block-form frontmatter)
examples/lifesciences/                               # +8 runnable synthetic examples
tests/unit/test_<workflow>.py                        # +8 test modules (exact == assertions)
```

**No new package, no new MCP domain string, no `pyproject.toml` package-data row** — `lifesciences/skills/templates/*` glob and the `"lifesciences"` SKILLS_DOMAIN registration already exist. Additive siblings only; library core (`core/`) and all 27 existing workflows untouched.

---

## MVP-8 workflow specs

Legend: **[veto]** uses the reviewer-veto halt pattern. All gates additionally require `review.approved`. Numeric regulatory tokens live only in prose/fields/criteria, never in a flag header.

### 1. `HCTPClassificationWorkflow` [veto] — Advanced therapies

Classify a human cell/tissue product as a **361 HCT/P** (minimal manipulation + homologous use → no premarket approval) versus a **351 biologic** (requires a BLA). The executor argues the lower-burden 361 tier; the reviewer flags the manipulation, use, or systemic-effect facts that force 351. This is the canonical motivated-under-classification case in CGT.

- **`HCTPClassificationRequest` fields:** `product_description`, `cellular_tissue_source` (autologous / allogeneic; tissue type), `manufacturing_steps`, `minimal_manipulation_rationale`, `intended_use_homology` (homologous vs non-homologous), `combination_with_another_article`, `systemic_effect_or_metabolic_dependence`, `proposed_regulatory_tier`, `precedent_determinations`.
- **Flag classes:**
  - `MINIMAL-MANIPULATION FLAGS:` — processing alters the relevant biological characteristics of the cells/tissue beyond minimal manipulation.
  - `HOMOLOGOUS-USE FLAGS:` — the intended use is not homologous to the tissue's original basic function.
  - `TIER-CLASSIFICATION FLAGS:` — the 361-vs-351 determination is inconsistent with the manipulation, use, combination, or systemic-effect facts.
- **Gate:** `approved AND zero MINIMAL-MANIPULATION AND zero HOMOLOGOUS-USE AND zero TIER-CLASSIFICATION AND no veto`.
- **Veto trigger:** a 351 biologic asserted as a 361 HCT/P (more-than-minimal manipulation or non-homologous use present) — a classification that would bypass the BLA and misrepresent the product's regulatory status.
- **Approver:** Regulatory Affairs lead (CBER pathway) sign-off.
- **PRODUCTION_GAPS:** cell/tissue-processing manufacturing-execution system, 21 CFR 1271 tissue-reference / decision-tree engine, regulatory-precedent (Request-for-Designation / untitled-letter) database.

### 2. `CGTPotencyAssayWorkflow` [veto] — Advanced therapies. Boundary: distinct from `AssayPerformanceClaimWorkflow` (IVD performance claim) — this is a therapeutic MoA-linked lot-release biological-activity assay.

Assess whether a potency assay is an adequate, mechanism-linked measure for **lot release** of a live product. The executor argues the assay supports release; the reviewer flags the MoA-linkage or validation gaps that make the release claim unsupportable.

- **`PotencyAssayRequest` fields:** `product_description`, `mechanism_of_action`, `potency_assay_description` (matrix · readout), `moa_linkage_rationale`, `assay_validation_summary` (accuracy · precision · specificity · range), `acceptance_criteria`, `lot_release_claim`, `surrogate_or_matrix_justification`, `stability_indicating_evidence`.
- **Flag classes:**
  - `MOA-LINKAGE FLAGS:` — the assay readout is not demonstrably linked to the product's mechanism of action / clinical activity.
  - `LOT-RELEASE-CLAIM FLAGS:` — the release claim exceeds what the assay + acceptance criteria can support.
  - `ASSAY-VALIDATION FLAGS:` — validation (accuracy, precision, specificity, range, stability-indicating capability) is inadequate for a release-critical method.
- **Gate:** `approved AND zero of each AND no veto`.
- **Veto trigger:** releasing product on a potency assay that does not measure clinical activity — a patient-harm / misbranding exposure.
- **Approver:** CMC / Analytical Development + Quality Engineering sign-off.
- **PRODUCTION_GAPS:** bioassay LIMS, assay-qualification/validation records, mechanism-of-action / pharmacology knowledge base, lot-release / QC system.

### 3. `CGTComparabilityWorkflow` [veto] — Advanced therapies. Boundary: distinct from `BiosimilarComparabilityWorkflow` (well-characterized protein) — this is a living cell / viral-vector product with small autologous lots.

Decide whether a product after a manufacturing change (process, site, vector lot, scale) is **comparable**, or whether the change makes it a different product requiring new clinical data. The executor argues comparable; the reviewer flags the analytical or clinical gaps.

- **`ComparabilityRequest` fields:** `product_description`, `change_description` (process / site / vector-lot / scale), `pre_change_process_summary`, `post_change_process_summary`, `analytical_comparability_data`, `quality_attribute_panel` (identity · purity · potency · safety), `clinical_bridging_plan`, `risk_assessment_summary`.
- **Flag classes:**
  - `PROCESS-DELTA FLAGS:` — the change plausibly affects a critical quality attribute not addressed by the comparability package.
  - `ANALYTICAL-GAP FLAGS:` — the analytical panel is insufficient to conclude comparability (missing attribute, underpowered, wrong stage).
  - `CLINICAL-BRIDGE FLAGS:` — residual uncertainty requires clinical bridging the plan does not provide.
- **Gate:** `approved AND zero of each AND no veto`.
- **Veto trigger:** a post-change product asserted comparable where the gaps mean it is materially a different product — releasing/continuing without the required new clinical data.
- **Approver:** Regulatory Affairs + CMC lead sign-off.
- **PRODUCTION_GAPS:** process-historian + batch-record system, analytical-characterization database, stability database, comparability-protocol repository.

### 4. `DonorEligibilityWorkflow` [veto] — Advanced therapies (allogeneic). Boundary: distinct from healthcare `AdverseEventTriageWorkflow` (clinical care) — this is the manufacturer's 21 CFR 1271 Subpart C regulatory eligibility determination.

Determine donor eligibility for an allogeneic product under 21 CFR 1271 Subpart C: screening (risk-factor history) and testing (relevant communicable-disease agents). The executor determines eligible; the reviewer flags screening/testing gaps or an unsupported eligible call.

- **`DonorEligibilityRequest` fields:** `donation_type` (living / cadaveric; allogeneic), `donor_screening_summary` (risk-factor history), `donor_testing_summary` (relevant-communicable-disease-agent panel results), `agents_considered`, `plasma_dilution_assessment`, `physical_assessment_or_records_review`, `retesting_or_repeat_status`, `urgent_medical_need_flag`.
- **Flag classes:**
  - `SCREENING-GAP FLAGS:` — required risk-factor screening (history, physical, records) incomplete or misinterpreted.
  - `TESTING-GAP FLAGS:` — required communicable-disease testing missing, wrong method, or misread; plasma-dilution not addressed.
  - `INELIGIBLE-RELEASE FLAGS:` — an "eligible" determination made despite screening/testing evidence indicating ineligibility (or an urgent-medical-need path documented as routine eligibility).
- **Gate:** `approved AND zero of each AND no veto`.
- **Veto trigger:** releasing an allogeneic product from an ineligible or inadequately screened/tested donor — a communicable-disease transmission risk.
- **Approver:** Quality Assurance / Tissue-safety (donor-eligibility) officer sign-off.
- **PRODUCTION_GAPS:** donor-screening/eligibility record system, infectious-disease-testing LIMS, deviation / urgent-medical-need documentation, 21 CFR 1271 Subpart C determination log.
- **L-HEALTH-1 PHI caveat:** kept on this workflow's `first_draft` — donor screening/testing echoes individually identifiable donor risk-history and results.

### 5. `CGTDurabilityClaimWorkflow` [veto] — Advanced therapies. Boundary: distinct from `PromotionalOffLabelReviewWorkflow` (MLR of marketing copy vs approved label) — this substantiates a pre-approval clinical/labeling claim against follow-up data.

Review a proposed durability / curative labeling claim for a one-time therapy against the actual follow-up evidence. The executor drafts the claim; the reviewer flags claims the follow-up duration, censoring, or population cannot support.

- **`DurabilityClaimRequest` fields:** `product_description`, `proposed_claim` (durability / curative language), `pivotal_efficacy_summary`, `followup_duration_and_n` (median follow-up · censoring), `durability_evidence` (loss-of-response · redosing), `population_and_endpoint`, `comparator_or_natural_history`, `label_context`.
- **Flag classes:**
  - `DURABILITY-CLAIM FLAGS:` — the durability claim exceeds the observed follow-up duration / censoring.
  - `FOLLOWUP-EVIDENCE FLAGS:` — n, median follow-up, or loss-of-response data are insufficient to support the claimed persistence of effect.
  - `CURATIVE-LANGUAGE FLAGS:` — "cure" / permanent-benefit language not supported by the evidence or the endpoint.
- **Gate:** `approved AND zero of each AND no veto`.
- **Veto trigger:** a curative/durability claim the follow-up data cannot support — an overstatement with patient-harm / misbranding exposure.
- **Approver:** Regulatory Affairs + Medical Affairs sign-off.
- **PRODUCTION_GAPS:** clinical-study database (long-term follow-up), efficacy/durability registry, labeling-management system, biostatistics analysis dataset.

### 6. `RMATDesignationWorkflow` [no veto] — Advanced therapies

Assess eligibility for Regenerative Medicine Advanced Therapy designation (an expedited program). The executor argues eligibility; the reviewer flags preliminary-clinical-evidence stretch.

- **`RMATRequest` fields:** `product_description` (regenerative-medicine therapy type), `serious_condition_rationale`, `preliminary_clinical_evidence` (n · design · endpoint · effect), `unmet_medical_need`, `intent_to_address_unmet_need`, `available_therapy_landscape`, `prior_fda_interactions`.
- **Flag classes:**
  - `EVIDENCE-STRETCH FLAGS:` — the preliminary clinical evidence does not credibly indicate the therapy may address the condition (underpowered, wrong endpoint, uncontrolled).
  - `SERIOUS-CONDITION FLAGS:` — the condition does not meet the serious-or-life-threatening bar as characterized.
  - `UNMET-NEED FLAGS:` — the unmet-need / available-therapy analysis is overstated.
- **Gate:** `approved AND zero of each` (advisory eligibility analysis — no veto).
- **Approver:** Regulatory Strategy lead sign-off.
- **PRODUCTION_GAPS:** clinical-evidence database, expedited-program precedent archive, unmet-need / therapy-landscape database, FDA-interaction (meeting-minutes) archive.

### 7. `VectorSafetyWorkflow` [no veto] — Advanced therapies

Assess the genome-safety characterization of a vector-based product: replication-competent-retrovirus/lentivirus (RCR/RCL) testing, integration profile, insertional-mutagenesis and oncogenicity risk. The executor summarizes the safety case; the reviewer flags gaps.

- **`VectorSafetyRequest` fields:** `vector_description` (retro / lenti / AAV / other), `rcr_rcl_testing_summary`, `integration_profile_data`, `insertional_mutagenesis_assessment`, `oncogenicity_or_tumorigenicity_data`, `vector_copy_number`, `nonclinical_biodistribution`, `long_term_followup_plan`.
- **Flag classes:**
  - `RCR-RCL-RISK FLAGS:` — replication-competent-virus testing strategy or sensitivity inadequate for the vector class / dose.
  - `INSERTIONAL-MUTAGENESIS FLAGS:` — integration-site / clonality assessment insufficient to characterize insertional-mutagenesis risk.
  - `ONCOGENICITY FLAGS:` — tumorigenicity / oncogenicity evidence or long-term-follow-up plan inadequate for the risk profile.
- **Gate:** `approved AND zero of each` (advisory safety-analysis — no veto).
- **Approver:** Biosafety + Nonclinical Safety sign-off.
- **PRODUCTION_GAPS:** vector-characterization LIMS, RCR/RCL + integration-site-sequencing data, nonclinical biodistribution / tumorigenicity study database, long-term-follow-up registry.

### 8. `CGTLotReleaseSpecWorkflow` [no veto] — Advanced therapies

Audit proposed lot-release specifications for a small-lot, short-shelf-life product for coverage and adequacy. The executor summarizes the spec set; the reviewer flags coverage gaps and small-lot / shelf-life pressures.

- **`LotReleaseSpecRequest` fields:** `product_description`, `proposed_release_specifications` (identity · purity · potency · sterility · safety · viability), `lot_size_and_format` (autologous single-dose / allogeneic bank), `shelf_life_and_storage`, `rapid_or_real_time_methods` (short-shelf-life justification), `sterility_and_mycoplasma_strategy`, `out_of_specification_handling`, `stability_program_summary`.
- **Flag classes:**
  - `SPEC-COVERAGE FLAGS:` — a release-critical attribute (identity, purity, potency, sterility, safety, viability) lacks an adequate specification.
  - `SMALL-LOT FLAGS:` — sampling / test-consumption is impractical for the lot size, or acceptance criteria ignore small-lot statistics.
  - `SHELF-LIFE FLAGS:` — the rapid / real-time-release strategy for the short shelf life is inadequately justified (sterility / mycoplasma released before results).
- **Gate:** `approved AND zero of each` (advisory spec-adequacy audit — no veto).
- **Approver:** Quality Control + Quality Engineering sign-off.
- **PRODUCTION_GAPS:** QC LIMS, specification-management system, stability database, rapid-microbial-method validation records.

---

## Phase-2 catalog (4 locked designs)

Recorded so a later build is fill-in, not re-design. Flag hints illustrative; the 4th quality dimension + (where veto) the veto trigger are authored at build time in the batch plan. All hint headers are H-IND-1-clean (letters + spaces + hyphens).

| # | Workflow | Segment | Flag hint | Veto |
|---|----------|---------|-----------|------|
| 9 | `ViralVectorSheddingWorkflow` | Advanced therapies | `SHEDDING-PROFILE`, `CONTACT-RISK`, `ENVIRONMENTAL-CONTROL` | — |
| 10 | `ChainOfIdentityCustodyWorkflow` | Advanced therapies (autologous) | `IDENTITY-LINK`, `CUSTODY-GAP`, `MIXUP-RISK` | veto |
| 11 | `StartingMaterialQualificationWorkflow` | Advanced therapies | `SOURCE-QUALIFICATION`, `APHERESIS-ACCEPTANCE`, `TRACEABILITY` | — |
| 12 | `CellBankCharacterizationWorkflow` | Advanced therapies | `IDENTITY-PURITY`, `GENETIC-STABILITY`, `ADVENTITIOUS-AGENT` | — |

Phase-2 notes for the future builder:
- **#10 `ChainOfIdentityCustodyWorkflow` is veto** — an autologous chain-of-identity break (wrong-patient product) is a halt-worthy release exposure — and carries the **L-HEALTH-1 PHI caveat** (echoes an individual patient's identity linkage). It states a D-LIFESCI-2 boundary vs #1 `HCTPClassificationWorkflow` (regulatory tier vs per-lot identity chain).
- **#9 `ViralVectorSheddingWorkflow`** states a boundary vs `SterilityAssuranceWorkflow` (biosafety/environmental shedding, not product sterility).
- #11 / #12 are analytical/aggregate — no PHI caveat.

---

## Universal PRODUCTION_GAPS (all 8 MVP workflows)

Every workflow's `PRODUCTION_GAPS` docstring states the domain-wide caveat: these workflows are **decision-support, not decision-making**. A real deployment requires (a) the named source systems as live integrations rather than caller-pasted free text, (b) a qualified human approver whose role is printed as the checklist's first line, and (c) a hard stop that the LLM output is **never** auto-submitted to FDA / EMA / a notified body and is never a lot-release of record. FDA/EMA regulatory citations (21 CFR parts, ATMP regulation) are scenario framing, **not** legal or medical advice.

## Build sequence (MVP-8)

Lowest-risk / most-observable convergence first; veto workflows after the no-veto ones prove the loop; the PHI-caveat and boundary-sensitive veto workflow last:

1. `VectorSafetyWorkflow` (#7, no veto — self-contained safety audit)
2. `CGTLotReleaseSpecWorkflow` (#8, no veto)
3. `RMATDesignationWorkflow` (#6, no veto)
4. `CGTPotencyAssayWorkflow` (#2, veto — first veto workflow)
5. `HCTPClassificationWorkflow` (#1, veto — the canonical classification call)
6. `CGTComparabilityWorkflow` (#3, veto — validate the biosimilar boundary)
7. `CGTDurabilityClaimWorkflow` (#5, veto — validate the promo/MLR boundary)
8. `DonorEligibilityWorkflow` (#4, veto — validate the healthcare boundary + PHI-caveat handling)

Ship-audit after the sweep per the domain-ship cadence: focused `security-audit` subagent on the new surface; verify shared-helper inheritance (M-PC-1 / H-IND-1 / L-PC-5 / D-A11-1), the D-LIFESCI-3 tripwire extension, and any input-shape attack vector specific to the CGT request fields. Reviewer checks a–j from the batch-A/B audit template (dim↔flag-header mapping, threshold parity in criteria+test, veto audit-before-check ordering, PHI-caveat matrix, boundary docstrings, header hygiene, input bounding, exact `== [...]` assertions, no-brand).

## Operator actions outside the diff (think-first Q5)

All in-repo doc updates — no secrets, env vars, infra, or migrations. Folded into the build, surfaced in commit bodies:

- Add rows **D-LIFESCI-5** and **D-LIFESCI-6** to [`docs/decisions.md`](../../decisions.md).
- Extend the D-LIFESCI-3 tripwire denylist with base64-encoded CGT product / tooling brand seeds in `tests/unit/test_lifesciences_no_brand_names.py`.
- Update the project [`CLAUDE.md`](../../../CLAUDE.md) domain line: lifesciences **27 → 35** workflows, segment count **4 → 5**; refresh the total workflow + library-test counts.
- Update [`docs/NEXT_SESSION.md`](../../NEXT_SESSION.md) resume bookmark and the [`README.md`](../../../README.md) index.

## Compliance / naming constraint (load-bearing)

No brand or company name appears in any artifact of this segment — code, prompt template, example, test, or this spec. Scenarios use generic product **categories** ("an autologous CAR-T", "an AAV-vectored gene therapy", "an allogeneic iPSC-derived cell therapy"). The `_DISCLAIMER` (injected in code, per convention #10) reads as decision-support requiring qualified Regulatory Affairs / Quality / Tissue-safety / Biosafety sign-off, explicitly not a regulatory submission, not a lot-release of record, and not legal or medical advice.
