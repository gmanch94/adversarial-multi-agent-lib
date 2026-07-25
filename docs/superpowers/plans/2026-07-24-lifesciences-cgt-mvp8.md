# Lifesciences CGT/ATMP MVP-8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the 8 Cell & Gene Therapy (CGT/ATMP) workflows — the 5th lifesciences segment — as additive siblings, per [`2026-07-24-lifesciences-cgt-segment-design.md`](../specs/2026-07-24-lifesciences-cgt-segment-design.md).

**Architecture:** Each workflow is a self-contained module under `src/adv_multi_agent/lifesciences/workflows/` following the locked no-base-class recipe. 5 use the reviewer-veto halt pattern (copy skeleton = `substantial_equivalence_510k.py`); 3 are advisory no-veto (copy skeleton = `design_control_traceability.py`). Library `core/` and all 27 existing workflows are untouched. No new package, MCP domain string, or `pyproject.toml` row (all already exist for `lifesciences`).

**Tech Stack:** Python 3.11+, dataclasses, pytest + pytest-asyncio, `core._internal` shared helpers (`extract_flags`, `extract_veto_directive`, `sanitize_for_prompt`, `truncate_flag_display`), `core.workflow.BaseWorkflow`.

---

## The mechanical recipe (READ FIRST — every task applies this)

Every workflow is the skeleton copied verbatim with per-workflow deltas substituted. **Do not invent structure** — copy the named skeleton file, then change only the listed tokens.

### Veto skeleton (workflows #4–#8) — copy `src/adv_multi_agent/lifesciences/workflows/substantial_equivalence_510k.py`

Substitute, keeping every other line identical:
1. Module docstring (title, ARIS lineage line kept verbatim, `PRODUCTION_GAPS` list, boundary sentence where specified).
2. `_DISCLAIMER`, `_VETO_BANNER` strings.
3. `_FLAG_HEADERS` tuple (3 headers).
4. `_<X>_REVIEW_CRITERIA` — 5 dimensions (3 CRITICAL each mapping to one flag header, + PERFORMANCE/SUFFICIENCY 15% + ACTIONABILITY 10%), the VETO CRITERIA block, the L-PC-2 FORMAT NOTE (verbatim), the `Score >= 8.0 AND zero <each> AND no VETO` line, and the `End your review with exactly these lines:` block listing the 3 headers + `REVIEWER VETO:`.
5. `_INITIAL_PROMPT` sections + `_REVISION_PROMPT` flag guidance.
6. `<Request>` dataclass fields + `to_prompt_text()`.
7. Class name + convergence-gate docstring + all method bodies keep the veto machinery (`_extract_veto`, veto break BEFORE convergence, `_compose_output` with banner, `first_draft` in metadata, veto row in checklist).
8. `metadata` keys renamed to the workflow's flag classes; `_build_<x>_checklist` first line `[OWNER: <approver>]`.

**Gate (veto):** `review.approved AND not self._flag_classes_unresolved(review.critique, _FLAG_HEADERS, current.values())`, with the veto check breaking first. Never a bare `not any(...)` (D-A11-1).

### No-veto skeleton (workflows #1–#3) — copy `src/adv_multi_agent/lifesciences/workflows/design_control_traceability.py`

Same as above MINUS all veto machinery: no `_VETO_BANNER`, no `extract_veto_directive` import, no `_extract_veto`, no veto break, `output=f"{output}\n\n---\n\n{_DISCLAIMER}"`, no `veto_reason`/`vetoed`/`first_draft` metadata, no veto row in checklist. Criteria text uses `Score >= 7.5` and omits the VETO CRITERIA block + the `REVIEWER VETO:` emission line.

### Templates (4 per workflow) — copy the `se510k_*.md` set

Block-form YAML frontmatter (`name`, `description`, `inputs:` as a block sequence — REQUIRED post-`c1a7414` registry fix). `<slug>_initial.md` (inputs = every Request field), `<slug>_revision.md` (inputs: output, critique, suggestions, flags…), `<slug>_review.md` (inputs: output; body = the review criteria), `<slug>_checklist.md` (inputs = veto_reason [veto only] + flag lists + key fields). Body text mirrors the module's prompt/criteria/checklist strings.

### Example — copy `examples/lifesciences/substantial_equivalence_510k.py`

Swap the import, the `<Request>` construction (a synthetic **generic-category** scenario, no brand — veto examples exercise the veto path), and the print block (flag-list keys).

### H-IND-1 hard rule (applies to every header)

Every flag header is uppercase LETTERS + SPACES + HYPHENS only. **Watch `RCR-RCL-RISK FLAGS:` (#1) — the prose is `RCR/RCL` with a slash; the header MUST use hyphens.** Numeric tokens (361/351/1271/1394) live only in prose/fields/criteria, never in a header.

### Per-workflow TDD loop (identical for every Task N)

- [ ] **Step A:** Write `tests/unit/test_<module>.py` by copying `tests/unit/test_substantial_equivalence_510k.py` (veto) or the no-veto equivalent, substituting the Request fixture (generic scenario), flag headers, metadata keys, and the exact `==` critique assertions from this task's "Test fixtures" block.
- [ ] **Step B:** Run `python -m pytest tests/unit/test_<module>.py -v` → expect FAIL (module not found).
- [ ] **Step C:** Write `src/adv_multi_agent/lifesciences/workflows/<module>.py` from the skeleton + this task's deltas.
- [ ] **Step D:** Write the 4 templates + the example.
- [ ] **Step E:** Run `python -m pytest tests/unit/test_<module>.py -v` → expect PASS.
- [ ] **Step F:** Add `test_<module>.py` to the `lifesci_modules` set in `tests/unit/test_lifesciences_no_brand_names.py`; run `python -m pytest tests/unit/test_lifesciences_no_brand_names.py -v` → PASS.
- [ ] **Step G:** `ruff check` + `mypy` the new module; commit `feat(lifesciences): CGT #<n> <ClassName>`.

---

## Build order (spec §"Build sequence"): no-veto first, PHI/boundary veto last

Task 1 → #7 VectorSafety · Task 2 → #8 LotReleaseSpec · Task 3 → #6 RMAT · Task 4 → #2 Potency · Task 5 → #1 HCTP · Task 6 → #3 Comparability · Task 7 → #5 Durability · Task 8 → #4 DonorEligibility.

---

### Task 1: `VectorSafetyWorkflow` (no-veto) — spec #7

**Files:** Create `src/adv_multi_agent/lifesciences/workflows/vector_safety.py`, `tests/unit/test_vector_safety.py`, `examples/lifesciences/vector_safety.py`, `src/adv_multi_agent/lifesciences/skills/templates/vectorsafety_{initial,revision,review,checklist}.md`. Modify `tests/unit/test_lifesciences_no_brand_names.py`.

- **Class / Request:** `VectorSafetyWorkflow` / `VectorSafetyRequest`
- **Request fields:** `vector_description`, `rcr_rcl_testing_summary`, `integration_profile_data`, `insertional_mutagenesis_assessment`, `oncogenicity_or_tumorigenicity_data`, `vector_copy_number`, `nonclinical_biodistribution`, `long_term_followup_plan`
- **`_FLAG_HEADERS`:** `("RCR-RCL-RISK FLAGS:", "INSERTIONAL-MUTAGENESIS FLAGS:", "ONCOGENICITY FLAGS:")`
- **Criteria (5 dim):** 1. RCR/RCL TESTING ADEQUACY (30%, CRITICAL→RCR-RCL-RISK) · 2. INTEGRATION / INSERTIONAL-MUTAGENESIS (25%, CRITICAL→INSERTIONAL-MUTAGENESIS) · 3. ONCOGENICITY / TUMORIGENICITY (20%, CRITICAL→ONCOGENICITY) · 4. BIODISTRIBUTION & LONG-TERM FOLLOW-UP (15%) · 5. ACTIONABILITY (10%). Threshold 7.5.
- **Owner:** `Biosafety / Nonclinical Safety`
- **Docstring no-veto rationale:** audits characterization-strategy adequacy; a positive RCR/RCL or oncogenicity signal is a QC lot-release/disposition failure against spec (see `CGTLotReleaseSpecWorkflow`), not an adversarial-review halt.
- **PRODUCTION_GAPS:** vector-characterization LIMS · RCR/RCL + integration-site-sequencing data · nonclinical biodistribution/tumorigenicity study database · long-term-follow-up registry · qualified Biosafety approver gate (never auto-released) · dedicated third-model auditor (ARIS §3.1).
- **Test fixtures:** clean critique with all 3 headers `None detected`; non-converge critique with one `RCR-RCL-RISK FLAGS:` bullet → assert `metadata["rcr_rcl_risk_flags"] == ["<bullet text>"]`; sibling-stop critique with a trailing `RECOMMENDATION:` after the flag; metadata-keys test; disclaimer-in-output test; below-threshold (approved=False) non-converge.

### Task 2: `CGTLotReleaseSpecWorkflow` (no-veto) — spec #8

**Files:** `cgt_lot_release_spec.py`, `test_cgt_lot_release_spec.py`, `examples/lifesciences/cgt_lot_release_spec.py`, `lotrelease_{initial,revision,review,checklist}.md`. Modify brand test.

- **Class / Request:** `CGTLotReleaseSpecWorkflow` / `LotReleaseSpecRequest`
- **Request fields:** `product_description`, `proposed_release_specifications`, `lot_size_and_format`, `shelf_life_and_storage`, `rapid_or_real_time_methods`, `sterility_and_mycoplasma_strategy`, `out_of_specification_handling`, `stability_program_summary`
- **`_FLAG_HEADERS`:** `("SPEC-COVERAGE FLAGS:", "SMALL-LOT FLAGS:", "SHELF-LIFE FLAGS:")`
- **Criteria:** 1. RELEASE-ATTRIBUTE COVERAGE (30%, CRITICAL→SPEC-COVERAGE; identity/purity/potency/sterility/safety/viability) · 2. SMALL-LOT SAMPLING (25%, CRITICAL→SMALL-LOT) · 3. SHORT-SHELF-LIFE RELEASE (20%, CRITICAL→SHELF-LIFE; sterility/mycoplasma released before results) · 4. STABILITY & OOS HANDLING (15%) · 5. ACTIONABILITY (10%). Threshold 7.5.
- **Owner:** `Quality Control / Quality Engineering`
- **Docstring cross-ref:** potency-as-release-attribute *adequacy* (MoA-linkage) is `CGTPotencyAssayWorkflow`'s veto call; this audits whole-spec-set coverage only — do not duplicate the potency-linkage logic.
- **PRODUCTION_GAPS:** QC LIMS · specification-management system · stability database · rapid-microbial-method validation records · qualified QC approver gate · dedicated auditor.
- **Test fixtures:** as Task 1 with `SPEC-COVERAGE FLAGS:` as the exercised header → `metadata["spec_coverage_flags"]`.

### Task 3: `RMATDesignationWorkflow` (no-veto) — spec #6

**Files:** `rmat_designation.py`, `test_rmat_designation.py`, `examples/lifesciences/rmat_designation.py`, `rmat_{initial,revision,review,checklist}.md`. Modify brand test.

- **Class / Request:** `RMATDesignationWorkflow` / `RMATRequest`
- **Request fields:** `product_description`, `serious_condition_rationale`, `preliminary_clinical_evidence`, `unmet_medical_need`, `intent_to_address_unmet_need`, `available_therapy_landscape`, `prior_fda_interactions`
- **`_FLAG_HEADERS`:** `("EVIDENCE-STRETCH FLAGS:", "SERIOUS-CONDITION FLAGS:", "UNMET-NEED FLAGS:")`
- **Criteria:** 1. PRELIMINARY CLINICAL EVIDENCE (30%, CRITICAL→EVIDENCE-STRETCH; n/design/endpoint/effect credibly indicates potential) · 2. SERIOUS OR LIFE-THREATENING CONDITION (25%, CRITICAL→SERIOUS-CONDITION) · 3. UNMET MEDICAL NEED (20%, CRITICAL→UNMET-NEED; vs available-therapy landscape) · 4. REGENERATIVE-MEDICINE-THERAPY QUALIFICATION (15%) · 5. ACTIONABILITY (10%). Threshold 7.5.
- **Owner:** `Regulatory Strategy`
- **PRODUCTION_GAPS:** clinical-evidence database · expedited-program precedent archive · unmet-need/therapy-landscape database · FDA-interaction (meeting-minutes) archive · qualified RA approver gate · dedicated auditor.
- **Test fixtures:** exercised header `EVIDENCE-STRETCH FLAGS:` → `metadata["evidence_stretch_flags"]`.

### Task 4: `CGTPotencyAssayWorkflow` (veto) — spec #2

**Files:** `cgt_potency_assay.py`, `test_cgt_potency_assay.py`, `examples/lifesciences/cgt_potency_assay.py`, `potency_{initial,revision,review,checklist}.md`. Modify brand test.

- **Class / Request:** `CGTPotencyAssayWorkflow` / `PotencyAssayRequest`
- **Request fields:** `product_description`, `mechanism_of_action`, `potency_assay_description`, `moa_linkage_rationale`, `assay_validation_summary`, `acceptance_criteria`, `lot_release_claim`, `surrogate_or_matrix_justification`, `stability_indicating_evidence`
- **`_FLAG_HEADERS`:** `("MOA-LINKAGE FLAGS:", "LOT-RELEASE-CLAIM FLAGS:", "ASSAY-VALIDATION FLAGS:")`
- **Criteria:** 1. MOA LINKAGE (30%, CRITICAL→MOA-LINKAGE; readout demonstrably linked to mechanism/clinical activity) · 2. LOT-RELEASE CLAIM SUPPORT (25%, CRITICAL→LOT-RELEASE-CLAIM) · 3. ASSAY VALIDATION (20%, CRITICAL→ASSAY-VALIDATION; accuracy/precision/specificity/range/stability-indicating) · 4. SURROGATE / MATRIX JUSTIFICATION (15%) · 5. ACTIONABILITY (10%). Threshold 8.0.
- **Veto trigger:** releasing product on a potency assay that does not measure clinical activity — a patient-harm / misbranding exposure.
- **`_VETO_BANNER`:** reviewer found the potency assay inadequate to support lot release (not MoA-linked / not validated); releasing on it risks releasing product without demonstrated clinical activity. Escalate to CMC/Analytical + QE.
- **Boundary docstring:** distinct from `AssayPerformanceClaimWorkflow` (an IVD analytical/clinical performance claim) — this is a therapeutic MoA-linked biological-activity lot-release assay.
- **Owner:** `CMC / Analytical Development + Quality Engineering`
- **PRODUCTION_GAPS:** bioassay LIMS · assay-qualification/validation records · mechanism-of-action / pharmacology knowledge base · lot-release / QC system · qualified approver gate · dedicated auditor.
- **Test fixtures (veto shape):** clean; non-converge on `MOA-LINKAGE FLAGS:` → `metadata["moa_linkage_flags"]`; sibling-stop; **veto** critique (`REVIEWER VETO: <text>`) → `rounds==1`, `metadata["vetoed"] is True`, `first_draft` preserved, `_VETO_BANNER in output`; no-veto-when-None; metadata keys; disclaimer; below-threshold.

### Task 5: `HCTPClassificationWorkflow` (veto) — spec #1

**Files:** `hctp_classification.py`, `test_hctp_classification.py`, `examples/lifesciences/hctp_classification.py`, `hctp_{initial,revision,review,checklist}.md`. Modify brand test.

- **Class / Request:** `HCTPClassificationWorkflow` / `HCTPClassificationRequest`
- **Request fields:** `product_description`, `cellular_tissue_source`, `manufacturing_steps`, `minimal_manipulation_rationale`, `intended_use_homology`, `combination_with_another_article`, `systemic_effect_or_metabolic_dependence`, `proposed_regulatory_tier`, `precedent_determinations`
- **`_FLAG_HEADERS`:** `("MINIMAL-MANIPULATION FLAGS:", "HOMOLOGOUS-USE FLAGS:", "TIER-CLASSIFICATION FLAGS:")`
- **Criteria (enumerate all four 1271.10(a) prongs — spec MED fix):** 1. MINIMAL MANIPULATION — prong (1) (30%, CRITICAL→MINIMAL-MANIPULATION) · 2. HOMOLOGOUS USE — prong (2) (25%, CRITICAL→HOMOLOGOUS-USE) · 3. TIER CLASSIFICATION — prongs (3) not-combined-with-another-article AND (4) no systemic effect / not dependent on metabolic activity, feeding the overall 361-vs-351 call (25%, CRITICAL→TIER-CLASSIFICATION; the criteria text names prong 3 and prong 4 explicitly so they get forced attention, not buried) · 4. PRECEDENT CONSISTENCY (10%) · 5. ACTIONABILITY (10%). Threshold 8.0.
- **Veto trigger:** a 351 biologic asserted as a 361 HCT/P (more-than-minimal manipulation, non-homologous use, disqualifying combination, or systemic effect present) — bypasses the BLA and misrepresents regulatory status.
- **`_VETO_BANNER`:** reviewer found the product is a 351 biologic, not a 361 HCT/P; asserting the 361 tier would bypass the BLA and misrepresent regulatory status. Escalate to Regulatory Affairs (CBER pathway).
- **Scenario-scoping docstring note:** the 361 argument is only live for minimally-manipulated cellular/tissue products; genetically-modified cells and viral-vector gene therapies are categorically 351 and must not be authored as 361-candidate test cases. The example scenario is a minimally-processed structural-tissue / SVF-type product that a sponsor over-claims as 361.
- **Owner:** `Regulatory Affairs Lead (CBER pathway)`
- **PRODUCTION_GAPS:** cell/tissue-processing manufacturing-execution system · 21 CFR 1271 tissue-reference / decision-tree engine · regulatory-precedent (Request-for-Designation / untitled-letter) database · qualified RA approver gate · dedicated auditor.
- **Test fixtures:** exercised header `MINIMAL-MANIPULATION FLAGS:` → `metadata["minimal_manipulation_flags"]`; veto shape as Task 4.

### Task 6: `CGTComparabilityWorkflow` (veto) — spec #3

**Files:** `cgt_comparability.py`, `test_cgt_comparability.py`, `examples/lifesciences/cgt_comparability.py`, `comparability_{initial,revision,review,checklist}.md`. Modify brand test.

- **Class / Request:** `CGTComparabilityWorkflow` / `ComparabilityRequest`
- **Request fields:** `product_description`, `change_description`, `pre_change_process_summary`, `post_change_process_summary`, `analytical_comparability_data`, `quality_attribute_panel`, `clinical_bridging_plan`, `risk_assessment_summary`
- **`_FLAG_HEADERS`:** `("PROCESS-DELTA FLAGS:", "ANALYTICAL-GAP FLAGS:", "CLINICAL-BRIDGE FLAGS:")`
- **Criteria:** 1. PROCESS-CHANGE IMPACT (30%, CRITICAL→PROCESS-DELTA; change plausibly affects a critical quality attribute) · 2. ANALYTICAL COMPARABILITY COVERAGE (25%, CRITICAL→ANALYTICAL-GAP; panel sufficient to conclude comparability) · 3. CLINICAL BRIDGING SUFFICIENCY (20%, CRITICAL→CLINICAL-BRIDGE; residual uncertainty needs clinical bridge) · 4. RISK ASSESSMENT (15%) · 5. ACTIONABILITY (10%). Threshold 8.0.
- **Veto trigger:** a post-change product asserted comparable where the gaps mean it is materially a different product needing new clinical data.
- **`_VETO_BANNER`:** reviewer found the post-change product not demonstrably comparable — the change affects a critical quality attribute the package does not cover; treating it as comparable would ship a materially different product without the required clinical data. Escalate to RA + CMC.
- **Boundary docstring:** distinct from `BiosimilarComparabilityWorkflow` (a well-characterized recombinant-protein analytical-similarity exercise) — this is a living cell / viral-vector product with small patient-specific autologous lots.
- **Owner:** `Regulatory Affairs + CMC Lead`
- **PRODUCTION_GAPS:** process-historian + batch-record system · analytical-characterization database · stability database · comparability-protocol repository · qualified approver gate · dedicated auditor.
- **Test fixtures:** exercised header `PROCESS-DELTA FLAGS:` → `metadata["process_delta_flags"]`; veto shape.

### Task 7: `CGTDurabilityClaimWorkflow` (veto) — spec #5

**Files:** `cgt_durability_claim.py`, `test_cgt_durability_claim.py`, `examples/lifesciences/cgt_durability_claim.py`, `durability_{initial,revision,review,checklist}.md`. Modify brand test.

- **Class / Request:** `CGTDurabilityClaimWorkflow` / `DurabilityClaimRequest`
- **Request fields:** `product_description`, `proposed_claim`, `pivotal_efficacy_summary`, `followup_duration_and_n`, `durability_evidence`, `population_and_endpoint`, `comparator_or_natural_history`, `label_context`
- **`_FLAG_HEADERS`:** `("DURABILITY-CLAIM FLAGS:", "FOLLOWUP-EVIDENCE FLAGS:", "CURATIVE-LANGUAGE FLAGS:")`
- **Criteria:** 1. DURABILITY vs FOLLOW-UP DURATION (30%, CRITICAL→DURABILITY-CLAIM; claim exceeds observed follow-up/censoring) · 2. FOLLOW-UP EVIDENCE SUFFICIENCY (25%, CRITICAL→FOLLOWUP-EVIDENCE; n/median-follow-up/loss-of-response) · 3. CURATIVE LANGUAGE (20%, CRITICAL→CURATIVE-LANGUAGE; "cure"/permanent-benefit unsupported by endpoint) · 4. COMPARATOR / NATURAL-HISTORY CONTEXT (15%) · 5. ACTIONABILITY (10%). Threshold 8.0.
- **Veto trigger:** a curative/durability claim the follow-up data cannot support — an overstatement with patient-harm / misbranding exposure.
- **`_VETO_BANNER`:** reviewer found the durability/curative claim unsupported by the follow-up duration and data; making it would overstate benefit with misbranding exposure. Escalate to RA + Medical Affairs.
- **Boundary docstring:** distinct from `PromotionalOffLabelReviewWorkflow` (MLR review of marketing copy against an already-approved label) — this substantiates a pre-approval clinical/labeling claim against long-term follow-up data.
- **Owner:** `Regulatory Affairs + Medical Affairs`
- **PRODUCTION_GAPS:** clinical-study database (long-term follow-up) · efficacy/durability registry · labeling-management system · biostatistics analysis dataset · qualified approver gate · dedicated auditor.
- **Test fixtures:** exercised header `DURABILITY-CLAIM FLAGS:` → `metadata["durability_claim_flags"]`; veto shape.

### Task 8: `DonorEligibilityWorkflow` (veto, PHI caveat) — spec #4

**Files:** `donor_eligibility.py`, `test_donor_eligibility.py`, `examples/lifesciences/donor_eligibility.py`, `donor_{initial,revision,review,checklist}.md`. Modify brand test.

- **Class / Request:** `DonorEligibilityWorkflow` / `DonorEligibilityRequest`
- **Request fields:** `donation_type`, `donor_screening_summary`, `donor_testing_summary`, `agents_considered`, `plasma_dilution_assessment`, `physical_assessment_or_records_review`, `retesting_or_repeat_status`, `urgent_medical_need_flag`
- **`_FLAG_HEADERS`:** `("SCREENING-GAP FLAGS:", "TESTING-GAP FLAGS:", "INELIGIBLE-RELEASE FLAGS:")`
- **Criteria:** 1. DONOR SCREENING (30%, CRITICAL→SCREENING-GAP; risk-factor history/physical/records complete) · 2. COMMUNICABLE-DISEASE TESTING (25%, CRITICAL→TESTING-GAP; required agents, method, plasma-dilution) · 3. ELIGIBILITY DETERMINATION (20%, CRITICAL→INELIGIBLE-RELEASE; "eligible" call consistent with screening+testing; urgent-need path not mislabeled routine) · 4. PLASMA-DILUTION & URGENT-NEED DOCUMENTATION (15%) · 5. ACTIONABILITY (10%). Threshold 8.0.
- **Veto trigger:** releasing an allogeneic product from an ineligible or inadequately screened/tested donor — a communicable-disease transmission risk.
- **`_VETO_BANNER`:** reviewer found the donor ineligible or inadequately screened/tested; releasing the allogeneic product risks communicable-disease transmission. Escalate to QA / Tissue-safety officer; do not release.
- **Boundary docstring:** distinct from healthcare `AdverseEventTriageWorkflow` (clinical severity/causality for a provider) — this is the manufacturer's 21 CFR 1271 Subpart C regulatory eligibility determination.
- **L-HEALTH-1 PHI caveat:** `metadata["first_draft"]` carries the PHI-echo caveat prefix (mirror the exact pattern in `device_reportability.py`). Grep `L-HEALTH-1` in the repo before writing to copy the caveat string verbatim.
- **Owner:** `Quality Assurance / Tissue-Safety (Donor-Eligibility) Officer`
- **PRODUCTION_GAPS:** donor-screening/eligibility record system · infectious-disease-testing LIMS · deviation / urgent-medical-need documentation · 21 CFR 1271 Subpart C determination log · qualified approver gate · dedicated auditor.
- **Test fixtures:** exercised header `SCREENING-GAP FLAGS:` → `metadata["screening_gap_flags"]`; veto shape; **PHI-caveat test** — on the veto path assert the L-HEALTH-1 caveat token is present in `metadata["first_draft"]`.

---

### Task 9: Cross-cutting — decisions, docs, counts, full gate

**Files:** Modify `docs/decisions.md`, `CLAUDE.md`, `README.md`, `docs/NEXT_SESSION.md`, `docs/production-readiness-gaps.md`. Verify `tests/unit/test_registry.py` + any count assertions.

- [ ] **Step 1:** Append rows **D-LIFESCI-7** and **D-LIFESCI-8** to `docs/decisions.md` (text from spec §"Segment decisions").
- [ ] **Step 2:** Confirm all 8 `test_*.py` names were added to `lifesci_modules` (Steps F). Run `python -m pytest tests/unit/test_lifesciences_no_brand_names.py -v`.
- [ ] **Step 3:** Run `python -m pytest tests/unit/test_registry.py -v` — the files-on-disk == discovered guard must still pass with +32 templates. If it hardcodes a per-domain count, update the lifesciences number.
- [ ] **Step 4:** Update `CLAUDE.md`: lifesciences `27 → 35` workflows + segment `4 → 5` (add "advanced therapies (CGT/ATMP)"); refresh the workflow total (`63 → 71`), library-test count, and skill-template count (`256 → 288`).
- [ ] **Step 5:** Update `README.md` index + `docs/NEXT_SESSION.md` resume bookmark; note the CGT segment shipped in `docs/production-readiness-gaps.md` if it references the lifesciences catalog as "27/27 COMPLETE".
- [ ] **Step 6 (FULL GATE):** `ruff check .` · `mypy src` · `python -m pytest tests/unit -q`. All green.
- [ ] **Step 7:** Ship-audit — spawn an independent `security-audit`/reviewer subagent on the 8 new modules (checks a–j from the batch-A/B template: dim↔flag-header mapping, threshold parity, veto audit-before-check ordering, shared-helper inheritance, PHI-caveat matrix, boundary docstrings, header hygiene, input bounding, exact `==` assertions, no-brand). Fix findings pre-push.
- [ ] **Step 8:** Commit + push the batch (docs commit may use `[skip ci]`; code commits must not).

---

## Self-Review

**Spec coverage:** All 8 MVP workflows (Tasks 1–8) + decisions/docs/tripwire/counts (Task 9). Phase-2 four are design-only (not in this plan — correct). Every spec §MVP-8 workflow maps to a task; every operator-action from spec §"Operator actions" maps to a Task-9 step.

**Placeholder scan:** No TBD/TODO. Each task carries exact field lists, header tuples, criteria weights, veto triggers, owners, and test-assertion targets. The one deliberate "grep before writing" (Task 8 L-HEALTH-1 caveat string) is a lookup of an existing verbatim token, not a placeholder.

**Type consistency:** Class names, Request names, `_FLAG_HEADERS`, and `metadata[...]` snake_case keys are consistent within each task and derived mechanically from the headers (e.g. `RCR-RCL-RISK FLAGS:` → `metadata["rcr_rcl_risk_flags"]`). No dimension count varies (always 5, three CRITICAL mapped to the three headers). Veto vs no-veto skeleton is fixed by build-order (Tasks 1–3 no-veto, 4–8 veto).
