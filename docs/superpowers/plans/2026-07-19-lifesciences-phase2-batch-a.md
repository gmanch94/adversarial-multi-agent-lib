# Lifesciences Phase-2 Batch A (#9–16) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Execution note (advisor 2026-07-19):** in-session sequential, commit-per-workflow is preferred over subagent-driven for this batch — both on-disk skeletons are already in context and subagent dispatch re-loads them per task. Commit per workflow either way so a mid-build stop stays durable.

**Goal:** Build the first 8 of the 19 locked lifesciences Phase-2 workflows (catalog #9–16) as additive sibling modules, following the proven no-base-class recipe; leave #17–27 as batch B.

**Architecture:** Each workflow is an independent `BaseWorkflow` subclass cloned from one of two on-disk lifesciences skeletons (no-veto or veto), with domain-specific content substituted. No shared base class (D-LIFESCI-1 / D-IND-1 lineage). Purely additive — no wiring changes (pyproject package-data glob + MCP `SKILLS_DOMAIN` already cover lifesciences). The only cross-cutting edit is extending the D-LIFESCI-3 brand tripwire's hardcoded `tests/unit` module set.

**Tech Stack:** Python 3.11+, dataclasses, `adv_multi_agent.core._internal` shared helpers (`extract_flags`, `extract_veto_directive`, `sanitize_for_prompt`, `truncate_flag_display`), `core.workflow.BaseWorkflow`, pytest + pytest-asyncio.

---

## Source of truth

- **Design doc:** [`docs/superpowers/specs/2026-07-19-lifesciences-domain-design.md`](../specs/2026-07-19-lifesciences-domain-design.md) §"Phase-2 catalog (19 locked designs)". This plan expands catalog rows #9–16 (name / segment / 3 flag-hints / veto) into full workflow specs. **The catalog left everything except those four attributes as one-liners — the Request fields, approver, PRODUCTION_GAPS, 5-dimension criteria, and veto trigger authored below ARE the substantive design work and the content the self-review + ship-audit must verify.**
- **No-veto skeleton (clone this):** `src/adv_multi_agent/lifesciences/workflows/design_control_traceability.py` (#7).
- **Veto skeleton (clone this):** `src/adv_multi_agent/lifesciences/workflows/device_reportability.py` (#4).
- **No-veto test skeleton:** `tests/unit/test_design_control_traceability.py`.
- **Veto test skeleton:** `tests/unit/test_device_reportability.py`.
- **Example skeleton:** `examples/healthcare/adverse_event_triage.py` shape (already lifesciences-mirrored in `examples/lifesciences/`).
- **Skill-template skeleton:** `src/adv_multi_agent/lifesciences/skills/templates/design_{initial,revision,review,checklist}.md` — 4 per workflow; the `_review.md` = the module's criteria constant + frontmatter + `REVIEW:\n{output}` tail; `_initial`/`_revision`/`_checklist` mirror the module's other constants.

## Shared conventions (apply to EVERY workflow task; do not re-state per task)

Every workflow produces the same 6-file set:

1. `src/adv_multi_agent/lifesciences/workflows/<module>.py`
2. `tests/unit/test_<module>.py`
3. `examples/lifesciences/<module>.py`
4. `src/adv_multi_agent/lifesciences/skills/templates/<prefix>_initial.md`
5. `src/adv_multi_agent/lifesciences/skills/templates/<prefix>_revision.md`
6. `src/adv_multi_agent/lifesciences/skills/templates/<prefix>_review.md`
7. `src/adv_multi_agent/lifesciences/skills/templates/<prefix>_checklist.md`

**Clone-then-substitute procedure** (mechanical parts are proven — do not re-derive):

- Copy the matching skeleton module verbatim, then replace ONLY: module docstring (+ PRODUCTION_GAPS), `_DISCLAIMER`, `_VETO_BANNER` (veto only), `_FLAG_HEADERS`, the criteria constant, `_INITIAL_PROMPT` / `_REVISION_PROMPT` section bodies, the `*Request` dataclass (8 fields + `to_prompt_text`), the class name + docstring, the metadata keys, `_format_flag_section` banners, and `_build_*_checklist` owner + items. Leave the run-loop control flow, veto ordering (audit-write BEFORE veto-check; veto breaks first), `sanitize_for_prompt` caps, and `extract_flags` / `extract_veto_directive` calls byte-for-byte identical.
- **Threshold (advisor check — set in BOTH the criteria string AND the test `make_config`):** veto workflows `score_threshold=8.0`; no-veto workflows `7.5`.
- **5-dimension criteria shape (advisor check — 3 flag dims + 2 quality dims):** dims 1–3 are the three CRITICAL flag classes at weights 30/25/20, each ending "Flag ... under `<HEADER> FLAGS:`."; dim 4 is a domain-quality dim at 15% (no flag); dim 5 is `ACTIONABILITY (10%)` (no flag). Mirror the exact "End your review with exactly these lines:" block from the skeleton (list every flag header; veto workflows append the `REVIEWER VETO:` line + the L-PC-2 FORMAT NOTE).
- **H-IND-1 flag-header safety:** every header below is uppercase letters + spaces + hyphens only — zero digits/slashes/parens. The shared `_is_sibling_header_lhs` regex covers all; NO `core/_internal.py` change.
- **L-HEALTH-1 PHI caveat (advisor — subset trap):** the veto skeleton carries a `# L-HEALTH-1: ... first_draft may echo caller PHI` comment on `metadata["first_draft"]`. KEEP it ONLY on **#16 PharmacovigilanceSignal** (handles case-level patient data). DELETE it on **#12 BatchReleaseDeviation** (batch/mfg data) and **#15 ClinicalProtocolDesign** (pre-study design) — no patient PHI there; leaving it is a wrong caveat a cloner will ship on all three.
- **Boundary docstring + test:** only **#16** needs one (vs healthcare `AdverseEventTriageWorkflow`: #16 = aggregate signal → labeling impact; AdverseEventTriage = single-case severity/causality). #9–15 have no boundary collision — no boundary note.
- **No brand/company names anywhere (D-LIFESCI-3):** all example scenarios + test fixtures use generic product **categories** ("a continuous glucose monitor", "an adult nutritional shake", "an oral solid-dose tablet line"). Regulatory citations (21 CFR / ICH / ISO) are scenario context, not legal advice.
- **Test shape (F2 lesson — exact `== [...]`, never `any(substr in f)`):** clone the matching test skeleton. Non-veto tests clone `test_design_control_traceability.py` (classes: `TestRequestToPromptText`, `TestConvergence` with `converges_clean` / `does_not_converge_when_<flag>_present` / `stops_at_sibling_header`, `TestMetadata`, `TestDisclaimer`, `TestScoreThresholdBoundary`). Veto tests clone `test_device_reportability.py` (adds `TestVeto` with `veto_halts_loop` / `no_veto_when_directive_is_none`; #16 also adds `test_module_docstring_states_healthcare_boundary`). Every flag assertion uses `== ["<exact flag text>"]`. The `stops_at_sibling_header` test injects a `RECOMMENDATION:` line between the first flag block and the next flag header and asserts the first flag list is unchanged.
- **Metadata keys:** `<flag>_flags` (snake_case of each header), `<domain>_checklist`, one short sanitized summary field (200-char cap), `disclaimer`, `ledger_summary`; veto adds `veto_reason` + `vetoed` + `first_draft` when vetoed.
- **PRODUCTION_GAPS docstring:** name the live source systems + the qualified-approver gate + the "never auto-submitted" hard stop + the dedicated third-model auditor (ARIS §3.1), mirroring the skeleton's 5–6 numbered items.
- **Commit per workflow.** PowerShell inline `-m` only; no `&`, `>`, `<`, `|`, `&&` in the message (use words).

---

### Task 0: Extend the D-LIFESCI-3 tripwire module set + confirm state

**Files:**
- Modify: `tests/unit/test_lifesciences_no_brand_names.py:47-56` (the `lifesci_modules` set)

- [ ] **Step 1: Confirm clean state**

Run: `git -C . status --short --branch` and `git log --oneline -1`
Expected: clean tree, HEAD `dac205f` (lifesciences MVP-8 docs commit), on `main`.

- [ ] **Step 2: Add the 8 batch-A test filenames to the tripwire scan set**

The `tests/unit` scan uses a hardcoded set (there is no lifesciences-only test prefix to glob). New test files are NOT scanned until named here; each name is guarded by `.exists()` so adding them before the files exist is harmless (they are skipped). In `_lifesciences_files`, extend `lifesci_modules` with:

```python
        "test_gxp_data_integrity.py",
        "test_computer_system_validation.py",
        "test_stability_shelf_life.py",
        "test_batch_release_deviation.py",
        "test_cmo_qualification.py",
        "test_udi_labeling.py",
        "test_clinical_protocol_design.py",
        "test_pharmacovigilance_signal.py",
```

- [ ] **Step 3: Verify the tripwire still passes (new names skip cleanly)**

Run: `python -m pytest tests/unit/test_lifesciences_no_brand_names.py -q`
Expected: PASS (parametrized cases for the 8 new names are absent because the files do not exist yet; existing cases still pass).

- [ ] **Step 4: Commit**

```bash
git add tests/unit/test_lifesciences_no_brand_names.py
git commit -m "test(lifesciences): register 8 Phase-2 batch-A test modules in D-LIFESCI-3 tripwire scan set"
```

---

### Task 1: #9 GxPDataIntegrityWorkflow (no-veto · Cross)

**Files:**
- Create: `src/adv_multi_agent/lifesciences/workflows/gxp_data_integrity.py` (clone `design_control_traceability.py`)
- Create: `tests/unit/test_gxp_data_integrity.py` (clone `test_design_control_traceability.py`)
- Create: `examples/lifesciences/gxp_data_integrity.py`
- Create: `src/adv_multi_agent/lifesciences/skills/templates/gxp_{initial,revision,review,checklist}.md`

**Spec:**
- Class `GxPDataIntegrityWorkflow` · Request `GxPDataIntegrityRequest` · prefix `gxp` · threshold **7.5** · no veto.
- Owner (checklist first line): `[OWNER: Quality Assurance / Data Integrity Lead]`
- Summary metadata field: `system_description` (200-char cap).
- **8 Request fields:** `system_description` (GxP system/record category + role), `record_type` (electronic/paper/hybrid + which records), `audit_trail_summary` (audit-trail config + review evidence), `access_control_summary` (user roles, segregation of duties), `data_lifecycle_summary` (create→archive handling), `alcoa_assessment` (caller's ALCOA+ self-assessment), `deviations_investigations` (known DI deviations + CAPA), `review_by_exception_summary` (review-by-exception basis).
- **Flag headers:** `ALCOA FLAGS:` (an ALCOA+ attribute — attributable/legible/contemporaneous/original/accurate + complete/consistent/enduring/available — not demonstrably met) · `AUDIT-TRAIL FLAGS:` (audit trail missing, disabled, not reviewed, or editable) · `ATTRIBUTION FLAGS:` (an action not uniquely attributable to a person + time; shared logins; back-dating).
- **5-dim criteria:** 1. ALCOA+ COMPLIANCE (30%, CRITICAL → ALCOA FLAGS) · 2. AUDIT-TRAIL ADEQUACY (25%, CRITICAL → AUDIT-TRAIL FLAGS) · 3. ATTRIBUTION & ACCESS CONTROL (20%, CRITICAL → ATTRIBUTION FLAGS) · 4. DATA-LIFECYCLE COVERAGE (15%, quality — create-to-archive gaps) · 5. ACTIONABILITY (10%).
- **PRODUCTION_GAPS:** eQMS audit-trail review tooling; source systems (LIMS/MES/historian) as live integrations not pasted text; ALCOA+ assessment framework; data-governance council sign-off; dedicated third-model DI auditor (ARIS §3.1); output never a data-integrity attestation of record.
- **Example scenario (generic):** a chromatography data system (CDS) on a QC lab bench where audit trail was reviewable but not routinely reviewed, and one shared analyst login existed for a legacy instrument.
- **Test flag value:** in `does_not_converge_when_alcoa_flags_present`, critique `ALCOA FLAGS:\n- Contemporaneous recording not demonstrated for the legacy instrument` → assert `metadata["alcoa_flags"] == ["Contemporaneous recording not demonstrated for the legacy instrument"]`.

- [ ] **Step 1: Write the module** — clone the no-veto skeleton; substitute all content above.
- [ ] **Step 2: Write the test** — clone `test_design_control_traceability.py`; substitute request defaults (generic CDS scenario), flag headers, metadata keys, exact flag assertion.
- [ ] **Step 3: Write the example + 4 skill templates.**
- [ ] **Step 4: Run** `python -m pytest tests/unit/test_gxp_data_integrity.py -q` → Expected: PASS.
- [ ] **Step 5: Commit** `git commit -m "feat(lifesciences): add GxPDataIntegrityWorkflow (no-veto, ALCOA+ data integrity)"`

---

### Task 2: #10 ComputerSystemValidationWorkflow (no-veto · Cross)

**Files:** module `computer_system_validation.py` · test `test_computer_system_validation.py` · example · templates prefix `csv` (clone no-veto skeleton).

**Spec:**
- Class `ComputerSystemValidationWorkflow` · Request `ComputerSystemValidationRequest` · prefix `csv` · threshold **7.5** · no veto.
- Owner: `[OWNER: Computer System Validation / Quality IT]`
- Summary field: `system_description`.
- **8 fields:** `system_description` (system + GxP use), `intended_use_statement`, `gamp_category` (caller's GAMP 5 category claim), `requirements_summary` (URS/FS), `risk_assessment_summary`, `test_evidence_summary` (IQ/OQ/PQ evidence), `trace_matrix_summary` (requirement→test links), `change_control_summary`.
- **Flag headers:** `INTENDED-USE FLAGS:` (validation scope not matched to the stated GxP intended use / GAMP category) · `TRACE-GAP FLAGS:` (a requirement with no linked test, or a test with no requirement) · `TEST-EVIDENCE FLAGS:` (a requirement asserted verified without cited IQ/OQ/PQ evidence).
- **5-dim criteria:** 1. INTENDED-USE & RISK FIT (30%, CRITICAL → INTENDED-USE FLAGS) · 2. REQUIREMENT-TEST TRACEABILITY (25%, CRITICAL → TRACE-GAP FLAGS) · 3. TEST EVIDENCE (20%, CRITICAL → TEST-EVIDENCE FLAGS) · 4. RISK-BASED VALIDATION RIGOR (15%, quality — GAMP 5 effort proportionate to risk/category) · 5. ACTIONABILITY (10%).
- **PRODUCTION_GAPS:** validation-lifecycle tool (e.g. ValGenesis-class); requirements/traceability tool; test-management system; GAMP 5 risk framework; QA/CSV approver gate; never a validation certificate of record; third-model auditor (ARIS §3.1).
- **Example scenario:** a cloud-hosted eQMS module classified GAMP category 4 where two configuration requirements had no linked OQ test.
- **Test flag value:** `TRACE-GAP FLAGS:\n- Configuration requirement URS-014 has no linked OQ test` → assert `metadata["trace_gap_flags"] == ["Configuration requirement URS-014 has no linked OQ test"]`.

- [ ] **Step 1–5:** module → test → example + templates → `pytest tests/unit/test_computer_system_validation.py -q` (PASS) → commit `feat(lifesciences): add ComputerSystemValidationWorkflow (no-veto, GAMP 5 CSV)`.

---

### Task 3: #11 StabilityShelfLifeWorkflow (no-veto · Pharma/Nutrition)

**Files:** module `stability_shelf_life.py` · test `test_stability_shelf_life.py` · example · templates prefix `stability` (clone no-veto skeleton).

**Spec:**
- Class `StabilityShelfLifeWorkflow` · Request `StabilityShelfLifeRequest` · prefix `stability` · threshold **7.5** · no veto.
- Owner: `[OWNER: Stability / Analytical Sciences Lead]`
- Summary field: `product_description`.
- **8 fields:** `product_description` (product category + form), `proposed_shelf_life`, `storage_conditions` (long-term + accelerated), `stability_data_summary` (timepoints, batches, attributes), `specification_limits`, `trend_analysis_summary`, `oos_oot_events` (out-of-spec / out-of-trend history), `extrapolation_basis` (ICH Q1E argument for extrapolating beyond real-time data).
- **Flag headers:** `EXTRAPOLATION FLAGS:` (proposed shelf life extrapolated beyond what ICH Q1E + the data support) · `TREND FLAGS:` (a downward/degradation trend the proposal ignores) · `SPEC-EXCEEDANCE FLAGS:` (a data point at/over specification treated as passing, or an OOS not investigated).
- **5-dim criteria:** 1. EXTRAPOLATION JUSTIFICATION (30%, CRITICAL → EXTRAPOLATION FLAGS) · 2. TREND ANALYSIS (25%, CRITICAL → TREND FLAGS) · 3. SPECIFICATION CONFORMANCE (20%, CRITICAL → SPEC-EXCEEDANCE FLAGS) · 4. STATISTICAL-MODEL FIT (15%, quality — ICH Q1E poolability / regression appropriateness) · 5. ACTIONABILITY (10%).
- **PRODUCTION_GAPS:** stability-chamber LIMS; stability data-management + ICH Q1E trending engine; specification database; OOS/OOT investigation system; approver gate; never a shelf-life-of-record determination; third-model auditor.
- **Example scenario:** an oral solid-dose tablet proposing a 36-month shelf life extrapolated from 12 months of long-term data plus 6 months accelerated, with a slight assay downward drift.
- **Test flag value:** `EXTRAPOLATION FLAGS:\n- 36-month claim extrapolates beyond ICH Q1E limit for 12 months real-time data` → assert `metadata["extrapolation_flags"] == ["36-month claim extrapolates beyond ICH Q1E limit for 12 months real-time data"]`.

- [ ] **Step 1–5:** module → test → example + templates → `pytest tests/unit/test_stability_shelf_life.py -q` (PASS) → commit `feat(lifesciences): add StabilityShelfLifeWorkflow (no-veto, ICH Q1E shelf-life)`.

---

### Task 4: #13 CMOQualificationWorkflow (no-veto · Cross)

**Files:** module `cmo_qualification.py` · test `test_cmo_qualification.py` · example · templates prefix `cmo` (clone no-veto skeleton).

**Spec:**
- Class `CMOQualificationWorkflow` · Request `CMOQualificationRequest` · prefix `cmo` · threshold **7.5** · no veto.
- Owner: `[OWNER: Supplier Quality / External Manufacturing]`
- Summary field: `supplier_description`.
- **8 fields:** `supplier_description` (CMO/CDMO category + scope of work), `audit_findings_summary` (last audit observations + classification), `gmp_history` (regulatory inspection history / 483s / warning letters), `data_integrity_posture`, `capacity_assessment` (declared vs required capacity), `quality_agreement_status`, `capa_status` (open CAPAs from prior audits), `technical_transfer_readiness`.
- **Flag headers:** `GMP-GAP FLAGS:` (a GMP deficiency not remediated / no CAPA) · `DATA-INTEGRITY FLAGS:` (a DI weakness at the CMO not addressed) · `CAPACITY FLAGS:` (declared capacity/redundancy inadequate for the committed volume).
- **5-dim criteria:** 1. GMP COMPLIANCE (30%, CRITICAL → GMP-GAP FLAGS) · 2. DATA INTEGRITY (25%, CRITICAL → DATA-INTEGRITY FLAGS) · 3. CAPACITY & CONTINUITY (20%, CRITICAL → CAPACITY FLAGS) · 4. QUALITY-AGREEMENT COVERAGE (15%, quality — responsibilities/roles defined + CAPA linkage) · 5. ACTIONABILITY (10%).
- **PRODUCTION_GAPS:** supplier-qualification/audit system; quality-agreement repository; CAPA-sharing portal; supplier scorecard; approver gate; never a supplier-approval-of-record; third-model auditor.
- **Example scenario:** a sterile-fill CDMO with two prior major audit observations (one open CAPA on environmental monitoring) declaring capacity for a new commercial volume.
- **Test flag value:** `GMP-GAP FLAGS:\n- Open CAPA on environmental monitoring not remediated before qualification` → assert `metadata["gmp_gap_flags"] == ["Open CAPA on environmental monitoring not remediated before qualification"]`.

- [ ] **Step 1–5:** module → test → example + templates → `pytest tests/unit/test_cmo_qualification.py -q` (PASS) → commit `feat(lifesciences): add CMOQualificationWorkflow (no-veto, supplier GMP qualification)`.

---

### Task 5: #14 UDILabelingWorkflow (no-veto · Devices)

**Files:** module `udi_labeling.py` · test `test_udi_labeling.py` · example · templates prefix `udi` (clone no-veto skeleton).

**Spec:**
- Class `UDILabelingWorkflow` · Request `UDILabelingRequest` · prefix `udi` · threshold **7.5** · no veto.
- Owner: `[OWNER: Regulatory Labeling / UDI Coordinator]`
- Summary field: `device_identifier`.
- **8 fields:** `device_identifier` (device category + model), `di_pi_structure` (Device Identifier + Production Identifier composition), `issuing_agency` (GS1 / HIBCC / ICCBBA), `gudid_record_summary` (attributes submitted to GUDID/EUDAMED), `label_artwork_summary` (human-readable + AIDC on each tier), `packaging_hierarchy` (each/inner/case tiers), `direct_marking_status` (if reusable), `regional_scope`.
- **Flag headers:** `IDENTIFIER FLAGS:` (DI/PI structure invalid for the issuing agency, or PI segments missing) · `GUDID-CONSISTENCY FLAGS:` (a GUDID/EUDAMED attribute inconsistent with the label/artwork) · `PACKAGING-TIER FLAGS:` (a packaging tier missing its UDI, or the hierarchy DI relationship broken).
- **5-dim criteria:** 1. IDENTIFIER STRUCTURE (30%, CRITICAL → IDENTIFIER FLAGS) · 2. GUDID/EUDAMED CONSISTENCY (25%, CRITICAL → GUDID-CONSISTENCY FLAGS) · 3. PACKAGING-TIER COVERAGE (20%, CRITICAL → PACKAGING-TIER FLAGS) · 4. LABEL-ARTWORK CONSISTENCY (15%, quality — human-readable + AIDC parity, direct-mark rules) · 5. ACTIONABILITY (10%).
- **PRODUCTION_GAPS:** labeling-management system; GUDID/EUDAMED submission gateway; artwork-management system; GS1/HIBCC issuing-agency registry; approver gate; never an auto-submitted UDI record; third-model auditor.
- **Example scenario:** a reusable surgical instrument whose case-level UDI was present but whose direct-mark DI did not match the label DI, and one GUDID brand-name attribute was stale.
- **Test flag value:** `GUDID-CONSISTENCY FLAGS:\n- GUDID brand attribute does not match current label artwork` → assert `metadata["gudid_consistency_flags"] == ["GUDID brand attribute does not match current label artwork"]`.

- [ ] **Step 1–5:** module → test → example + templates → `pytest tests/unit/test_udi_labeling.py -q` (PASS) → commit `feat(lifesciences): add UDILabelingWorkflow (no-veto, UDI/GUDID consistency)`.

---

### Task 6: #12 BatchReleaseDeviationWorkflow (VETO · Pharma)

**Files:** module `batch_release_deviation.py` · test `test_batch_release_deviation.py` · example · templates prefix `batchrelease` (clone `device_reportability.py` veto skeleton). **DELETE the L-HEALTH-1 PHI caveat comment on `first_draft`** — batch/mfg data, no patient PHI.

**Spec:**
- Class `BatchReleaseDeviationWorkflow` · Request `BatchReleaseRequest` · prefix `batchrelease` · threshold **8.0** · **veto**.
- Owner: `[OWNER: Qualified Person / Quality Release]`
- Summary field: `batch_identifier`.
- **8 fields:** `batch_identifier` (product category + lot), `deviation_description`, `deviation_classification` (caller's minor/major/critical call), `affected_cqas` (critical quality attributes impacted), `impact_assessment_summary`, `root_cause_summary`, `capa_status`, `proposed_disposition` (release / reject / rework).
- **Flag headers:** `CRITICALITY FLAGS:` (deviation criticality under-classified vs its CQA/patient-safety impact) · `IMPACT-ASSESSMENT FLAGS:` (impact on product quality/safety not fully assessed; affected CQA missed) · `RELEASE-RISK FLAGS:` (a proposed release with unresolved risk to the patient or the CQA).
- **5-dim criteria:** 1. DEVIATION CRITICALITY (30%, CRITICAL → CRITICALITY FLAGS) · 2. IMPACT ASSESSMENT (25%, CRITICAL → IMPACT-ASSESSMENT FLAGS) · 3. RELEASE-RISK JUDGMENT (20%, CRITICAL → RELEASE-RISK FLAGS) · 4. CAPA-LINKAGE / ROOT-CAUSE (15%, quality) · 5. ACTIONABILITY (10%).
- **VETO trigger:** a `release` disposition for a batch with an unresolved critical deviation affecting a CQA / patient safety — i.e. releasing a non-conforming batch into distribution. `_VETO_BANNER`: escalate to the QP; the batch must not be released until the deviation is resolved.
- **PRODUCTION_GAPS:** MES/EBR (electronic batch record); deviation/CAPA system; specification + CoA system; QP release register; approver gate; never an auto-release; third-model auditor.
- **Example scenario:** an oral solid-dose lot with a mid-compression tablet-weight excursion classified "minor" and proposed for release, where the excursion touches a content-uniformity CQA.
- **Test flag value (non-veto path):** `CRITICALITY FLAGS:\n- Weight excursion touching content-uniformity CQA under-classified as minor` → assert `metadata["criticality_flags"] == [...]`. **Veto test:** critique `REVIEWER VETO: The proposed release dispositions a batch with an unresolved critical deviation affecting a content-uniformity CQA; the batch must not be released. Escalate to the QP.` → assert `metadata["vetoed"] is True`, `"release" in output`, `metadata["first_draft"] == "initial draft"`.

- [ ] **Step 1–5:** module (delete PHI caveat) → veto test → example + templates → `pytest tests/unit/test_batch_release_deviation.py -q` (PASS) → commit `feat(lifesciences): add BatchReleaseDeviationWorkflow (veto, non-conforming release)`.

---

### Task 7: #15 ClinicalProtocolDesignWorkflow (VETO · Pharma/Device)

**Files:** module `clinical_protocol_design.py` · test `test_clinical_protocol_design.py` · example · templates prefix `protocol` (clone veto skeleton). **DELETE the L-HEALTH-1 PHI caveat** — pre-study design, no patient PHI.

**Spec:**
- Class `ClinicalProtocolDesignWorkflow` · Request `ClinicalProtocolRequest` · prefix `protocol` · threshold **8.0** · **veto**.
- Owner: `[OWNER: Clinical Development / Medical Monitor]`
- Summary field: `protocol_synopsis`.
- **8 fields:** `protocol_synopsis` (indication + phase + design), `primary_endpoint`, `secondary_endpoints`, `statistical_plan_summary` (power, sample size, analysis), `population_eligibility` (inclusion/exclusion), `safety_monitoring_plan` (DSMB, stopping rules), `known_risks` (product safety profile), `comparator_control`.
- **Flag headers:** `ENDPOINT FLAGS:` (primary endpoint not validated / not able to support the objective / surrogate misuse) · `POWER FLAGS:` (sample size / power inadequate to detect the effect, or assumptions unjustified) · `SAFETY-MONITORING FLAGS:` (monitoring/stopping rules inadequate for a known serious risk).
- **5-dim criteria:** 1. ENDPOINT VALIDITY (30%, CRITICAL → ENDPOINT FLAGS) · 2. STATISTICAL POWER (25%, CRITICAL → POWER FLAGS) · 3. SAFETY MONITORING (20%, CRITICAL → SAFETY-MONITORING FLAGS) · 4. ETHICS / POPULATION-APPROPRIATENESS (15%, quality — eligibility proportionate to risk, vulnerable-population safeguards) · 5. ACTIONABILITY (10%).
- **VETO trigger:** a protocol that exposes subjects to undue risk (inadequate safety monitoring / stopping rules for a known serious risk) OR is scientifically invalid such that it cannot support its primary objective — i.e. an IRB/EC should withhold approval. `_VETO_BANNER`: escalate to the Medical Monitor / IRB; the protocol must not proceed to submission as designed.
- **PRODUCTION_GAPS:** CTMS; protocol-authoring + biostatistics tooling; IRB/EC submission system; DSMB charter repository; approver gate; never an auto-submitted protocol; third-model auditor.
- **Example scenario:** a Phase 2 device trial powered on an optimistic effect size with a primary endpoint that is a non-validated surrogate, and no pre-specified stopping rule for a known bleeding risk.
- **Test flag value (non-veto):** `POWER FLAGS:\n- Sample size assumes an unjustified effect size; study is underpowered` → assert `metadata["power_flags"] == [...]`. **Veto test:** `REVIEWER VETO: The protocol lacks a stopping rule for a known serious bleeding risk, exposing subjects to undue risk; it must not proceed as designed. Escalate to the Medical Monitor.` → assert `metadata["vetoed"] is True`.

- [ ] **Step 1–5:** module (delete PHI caveat) → veto test → example + templates → `pytest tests/unit/test_clinical_protocol_design.py -q` (PASS) → commit `feat(lifesciences): add ClinicalProtocolDesignWorkflow (veto, subject-risk / endpoint validity)`.

---

### Task 8: #16 PharmacovigilanceSignalWorkflow (VETO · Pharma) — boundary vs healthcare

**Files:** module `pharmacovigilance_signal.py` · test `test_pharmacovigilance_signal.py` · example · templates prefix `pvsignal` (clone veto skeleton). **KEEP the L-HEALTH-1 PHI caveat** — case-level patient data. **ADD a boundary docstring** (D-LIFESCI-2 shape) + a `test_module_docstring_states_healthcare_boundary`.

**Spec:**
- Class `PharmacovigilanceSignalWorkflow` · Request `PVSignalRequest` · prefix `pvsignal` · threshold **8.0** · **veto**.
- Owner: `[OWNER: Pharmacovigilance / Safety Physician]`
- Summary field: `product_description`.
- **Boundary docstring (module + class):** "BOUNDARY (D-LIFESCI-2): distinct from the healthcare `AdverseEventTriageWorkflow` — that grades clinical severity/causality for a single adverse event for a provider; this evaluates an AGGREGATE safety signal (disproportionality across cases) and its labeling/regulatory impact for the marketing-authorization holder." The test asserts `"distinct from" in doc and "adverseeventtriage" in doc.replace(" ", "")` (mirror `test_device_reportability.py:107`).
- **8 fields:** `product_description` (product category), `signal_description` (the observed signal / adverse-event-of-interest), `data_source` (spontaneous DB / literature / disproportionality run), `case_series_summary` (aggregate case count + features), `disproportionality_metrics` (PRR/ROR/EBGM), `causality_assessment` (population-level), `current_labeling` (whether the event is already labeled), `proposed_action` (caller's routine/no-action/label-change call).
- **Flag headers:** `SIGNAL-STRENGTH FLAGS:` (signal strength under-stated vs the disproportionality + case evidence) · `CAUSALITY FLAGS:` (population-level causality dismissed without adequate basis) · `LABELING-IMPACT FLAGS:` (a labeling/regulatory-action implication not reflected in the proposed action).
- **5-dim criteria:** 1. SIGNAL STRENGTH (30%, CRITICAL → SIGNAL-STRENGTH FLAGS) · 2. CAUSALITY ASSESSMENT (25%, CRITICAL → CAUSALITY FLAGS) · 3. LABELING/REGULATORY IMPACT (20%, CRITICAL → LABELING-IMPACT FLAGS) · 4. BENEFIT-RISK / DATA-SOURCE ADEQUACY (15%, quality) · 5. ACTIONABILITY (10%).
- **VETO trigger:** a validated signal meeting the threshold for regulatory action / label change (e.g. a new serious identified risk) characterized as "no action" / routine — i.e. under-escalation of a signal that requires notification or labeling change. `_VETO_BANNER`: escalate to the Safety Physician / QPPV; the signal requires formal evaluation and likely labeling/regulatory action.
- **PRODUCTION_GAPS:** safety database (e.g. Argus-class); signal-detection/disproportionality engine (EVDAS/FAERS mining); literature-monitoring; PSUR/labeling-change workflow; approver gate; never an auto-filed signal determination; third-model auditor.
- **Example scenario:** an established oral product with a rising disproportionality metric for a serious hepatic event not currently labeled, where the caller proposes "continue routine monitoring."
- **Test flag value (non-veto):** `SIGNAL-STRENGTH FLAGS:\n- Disproportionality for the hepatic event understated relative to EBGM` → assert `metadata["signal_strength_flags"] == [...]`. **Veto test:** `REVIEWER VETO: A serious unlabeled hepatic signal meeting the threshold for labeling action is characterized as no-action; it requires formal evaluation and likely a labeling change. Escalate to the Safety Physician.` → assert `metadata["vetoed"] is True`. Include `test_module_docstring_states_healthcare_boundary`.

- [ ] **Step 1–5:** module (keep PHI caveat + boundary docstring) → veto test (+ boundary test) → example + templates → `pytest tests/unit/test_pharmacovigilance_signal.py -q` (PASS) → commit `feat(lifesciences): add PharmacovigilanceSignalWorkflow (veto, aggregate signal; distinct from healthcare)`.

---

### Task 9: Batch close — gate, ship-audit, docs refresh

**Files:**
- Modify: `docs/decisions.md` (append D-LIFESCI-5)
- Modify: `docs/superpowers/specs/2026-07-19-lifesciences-domain-design.md` (mark #9–16 BUILT in the Phase-2 table)
- Modify: `CLAUDE.md` (counts), `README.md` (counts), `docs/NEXT_SESSION.md` (bookmark), `docs/production-readiness-gaps.md` (§Lifesciences Phase-2 batch A)

- [ ] **Step 1: Full local gate**

Run in order:
```
python -m ruff check .
python -m mypy src
python -m pytest tests/unit -q
python -m pytest tests/unit/test_lifesciences_no_brand_names.py -q
```
Expected: ruff clean; mypy strict clean; all tests pass (library count ~914 + ~88 new ≈ ~1002 — record the ACTUAL number from output, do not hardcode this estimate); tripwire green with 8 new modules now scanned (69 parametrized cases). If any fail, fix before proceeding — never push red.

- [ ] **Step 2: Domain-ship security-audit subagent**

Dispatch an independent `general-purpose` (or `code-reviewer`) subagent, briefed blind, on the 8 new modules + tests. Brief: "Review these 8 new lifesciences Phase-2 workflow modules for correctness + security. Verify per module: (a) the 5 review dimensions map onto exactly the 3 declared flag headers + 2 quality dims; (b) `score_threshold` matches idiom (8.0 veto / 7.5 no-veto) in BOTH the criteria string and the test `make_config`; (c) veto trigger is domain-correct and the audit-write-before-veto-check ordering is intact; (d) shared-helper inheritance (M-PC-1 veto marker, H-IND-1 sibling-stop, L-PC-5 display cap) is unbroken; (e) L-HEALTH-1 PHI caveat present ONLY on #16, absent on #12/#15; (f) no brand/company names; (g) any input-shape injection vector specific to these request fields. Severity-tag findings CRITICAL/HIGH/MED/LOW + one-line ship verdict." Fix CRITICAL/HIGH before push; fold LOW per policy or log to gaps doc.

- [ ] **Step 3: Append D-LIFESCI-5 to decisions.md**

```
| D-LIFESCI-5 | Phase-2 batch A built: catalog #9–16 (GxP data-integrity, CSV, stability, batch-release[veto], CMO-qual, UDI, clinical-protocol[veto], PV-signal[veto]) shipped as additive siblings; #17–27 remain designed-not-built (batch B). #16 carries a D-LIFESCI-2 boundary docstring vs healthcare AdverseEventTriage; L-HEALTH-1 PHI caveat kept only on #16. No wiring/base-class change. |
```

- [ ] **Step 4: Mark #9–16 BUILT in the design-doc Phase-2 table** (append " — BUILT (batch A)" to rows 9–16, or a status column note).

- [ ] **Step 5: Refresh counts** — CLAUDE.md + README: workflows 44 → **52**; lifesciences "8 MVP of 27" → "16 of 27 (MVP-8 + Phase-2 batch A)"; skill templates 180 → **212**; library test count → the actual `pytest -q` number. Update `docs/NEXT_SESSION.md` top banner (batch A shipped; batch B = #17–27 next) and `docs/production-readiness-gaps.md` with a §Lifesciences Phase-2 batch A entry (gate result + audit verdict).

- [ ] **Step 6: Commit the code batch's docs** — the workflow commits (Tasks 1–8) already landed. This final docs commit:

```bash
git add docs/decisions.md docs/superpowers/specs/2026-07-19-lifesciences-domain-design.md CLAUDE.md README.md docs/NEXT_SESSION.md docs/production-readiness-gaps.md
git commit -m "docs(lifesciences): mark Phase-2 batch A (#9-16) shipped; refresh counts, decisions, bookmark, gaps [skip ci]"
```

- [ ] **Step 7: Push** (per CLAUDE.md default ship-flow) — only if gate green AND no unresolved CRITICAL/HIGH audit finding:

```bash
git push origin main
```

---

## Self-Review

**1. Spec coverage:** design-doc Phase-2 rows #9–16 → Tasks 1–8 (build order: 5 no-veto #9/#10/#11/#13/#14 first, then 3 veto #12/#15/#16 — lowest-risk-first per MVP-8 sequence). Rows #17–27 explicitly deferred to batch B. Tripwire drift → Task 0. Wiring → confirmed none needed (additive; pyproject glob + MCP domain already cover lifesciences; domain `__init__` is export-free; no count-pinning test except the tripwire set). Docs/decisions/audit → Task 9.

**2. Placeholder scan:** none — each workflow task names the exact clone-source, the 8 fields, 3 headers, 5 weighted dims, veto trigger (veto tasks), owner, PRODUCTION_GAPS, generic example, and the exact `== [...]` flag assertion. Mechanical run-loop deliberately references the two real on-disk skeletons (a file to clone, not a placeholder) per the MVP-8 precedent.

**3. Type/name consistency:** module ↔ test ↔ example ↔ template-prefix ↔ class ↔ Request ↔ metadata-key names verified aligned per task; all flag headers uppercase+space+hyphen (H-IND-1 safe); thresholds 8.0 veto / 7.5 no-veto stated for both criteria string and test; PHI caveat matrix (keep #16 only) and boundary (#16 only) stated once in shared conventions and echoed in the affected tasks.
