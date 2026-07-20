# Lifesciences Phase-2 Batch B (#17–27) Implementation Plan

> **Execution note (advisor 2026-07-20):** in-session sequential, commit-per-workflow — same call as batch A. The two on-disk idiom skeletons are already proven; subagent dispatch would re-load them per task. **Commit this plan first (docs-only `[skip ci]`), then build so a mid-build compaction resumes from git log** (one commit per workflow; make each message name the `#` that landed). Build order: 5 no-veto (#18/#20/#21/#22/#24) → 4 veto (#17/#19/#23/#25) → 2 judgment-veto last (#26/#27).

**Goal:** Build the last 11 of the 27-workflow lifesciences catalog (#17–27) as additive sibling modules, completing the catalog. Fill-in against the locked design doc, NOT new design (D-LIFESCI-1 = no base class).

**Architecture:** Each workflow is an independent `BaseWorkflow` subclass cloned from one of two on-disk lifesciences skeletons — no-veto `design_control_traceability.py`, veto `batch_release_deviation.py`. No shared base class. Purely additive: no wiring changes (pyproject package-data glob + MCP `SKILLS_DOMAIN` already cover lifesciences; domain `__init__` is export-free). Only cross-cutting edit = extend the D-LIFESCI-3 brand-tripwire module set (Task 0).

**Tech stack:** Python 3.11+, dataclasses, `core._internal` shared helpers (`extract_flags`, `extract_veto_directive`, `sanitize_for_prompt`, `truncate_flag_display`), `core.workflow.BaseWorkflow`, pytest + pytest-asyncio.

---

## Source of truth

- **Design doc:** [`docs/superpowers/specs/2026-07-19-lifesciences-domain-design.md`](../specs/2026-07-19-lifesciences-domain-design.md) §"Phase-2 catalog", rows #17–27 (name / segment / 3 flag-hints / veto). **Everything else — the 8 Request fields, owner, PRODUCTION_GAPS, 5-dimension criteria, veto trigger, generic example, exact test flag value — is authored below and IS the substantive design the self-review + ship-audit must verify.**
- **No-veto skeleton (clone):** `src/adv_multi_agent/lifesciences/workflows/design_control_traceability.py`
- **Veto skeleton (clone):** `src/adv_multi_agent/lifesciences/workflows/batch_release_deviation.py`
- **No-veto test skeleton:** `tests/unit/test_design_control_traceability.py`
- **Veto test skeleton:** `tests/unit/test_batch_release_deviation.py`
- **Example skeleton:** `examples/lifesciences/design_control_traceability.py` (no-veto) · any batch-A veto example for veto.
- **Skill-template skeleton:** `src/adv_multi_agent/lifesciences/skills/templates/{design,batchrelease}_{initial,revision,review,checklist}.md` — 4 per workflow.

## Shared conventions (apply to EVERY workflow; do not re-state per task)

Every workflow produces the same 6-file set (module, test, example, 4 templates):

1. `src/adv_multi_agent/lifesciences/workflows/<module>.py`
2. `tests/unit/test_<module>.py`
3. `examples/lifesciences/<module>.py`
4–7. `src/adv_multi_agent/lifesciences/skills/templates/<prefix>_{initial,revision,review,checklist}.md`

**Clone-then-substitute (mechanical parts are proven — do not re-derive):** copy the matching skeleton verbatim, replace ONLY: module docstring (+ PRODUCTION_GAPS), `_DISCLAIMER`, `_VETO_BANNER` (veto), `_FLAG_HEADERS`, the criteria constant, `_INITIAL_PROMPT` / `_REVISION_PROMPT` bodies, the `*Request` dataclass (8 fields + `to_prompt_text`), the class name + docstring, metadata keys, `_format_flag_section` banners, `_build_*_checklist` owner + items. Leave the run-loop control flow, veto ordering (audit-write BEFORE veto-check; veto breaks first), `sanitize_for_prompt` caps, and `extract_flags` / `extract_veto_directive` calls byte-for-byte identical.

- **Threshold (set in BOTH criteria string AND test `make_config`):** veto `score_threshold=8.0`; no-veto `7.5`.
- **5-dim criteria shape:** dims 1–3 = the three CRITICAL flag classes at 30/25/20, each ending "Flag ... under `<HEADER> FLAGS:`."; dim 4 = domain-quality dim at 15% (no flag); dim 5 = `ACTIONABILITY (10%)` (no flag). Mirror the skeleton's "End your review with exactly these lines:" block; veto workflows append `REVIEWER VETO:` + the L-PC-2 FORMAT NOTE.
- **H-IND-1 flag-header safety:** every header below is uppercase letters + spaces + hyphens only — zero digits/slashes/parens. `_is_sibling_header_lhs` covers all; **NO `core/_internal.py` change.**
- **L-HEALTH-1 PHI caveat (structurally veto-only — annotates `metadata["first_draft"]`):** KEEP the caveat comment ONLY on **#26 MedicalInformationResponse** (an unsolicited inquiry can quote a specific patient case). DELETE it on veto #17/#19/#23/#25/#27 (analytical / sterility / product-lot / aggregate-PK / aggregate-signal data — no individual PHI). No-veto workflows have no `first_draft`, so the caveat is absent by construction.
- **Boundary docstring + test (D-LIFESCI-2 shape, mirror `test_pharmacovigilance_signal.py:107`):** only **#26** (vs `PromotionalOffLabelReviewWorkflow`) and **#27** (vs `PharmacovigilanceSignalWorkflow`) need one. Test: `doc = mod.__doc__.lower(); assert "distinct from" in doc and "<otherclasslowercasenospaces>" in doc.replace(" ", "")`. #23/#25 have no genuine collision — no boundary. #9–#22/#24 none.
- **No brand/company names anywhere (D-LIFESCI-3) — author clean from the start.** Batch A shipped `e.g. ValGenesis`/`Argus` in PRODUCTION_GAPS and drew a MEDIUM. Write generic tool **categories** only — zero `e.g. <name>`. High-risk spaces this batch: #24 track-and-trace vendors, #20 SBOM/scanning tools, #22 HE-modeling software, #17 analytical instruments. Example scenarios + fixtures use generic product **categories** ("a refrigerated biologic", "a network-connected infusion pump", "an oral solid-dose tablet"). Regulatory citations (21 CFR / ICH / ISO / EU MDR) are scenario context, not legal advice.
- **Test shape (F2 — exact `== [...]`, never `any(substr in f)`):** clone the matching test skeleton. Non-veto → `test_design_control_traceability.py` (classes `TestRequestToPromptText`, `TestConvergence` with `converges_clean` / `does_not_converge_when_<flag>_present` / `stops_at_sibling_header` / a per-remaining-flag non-convergence + `converges_after_flag_cleared`, `TestMetadata`, `TestDisclaimer`, `TestScoreThresholdBoundary`). Veto → `test_batch_release_deviation.py` (adds `TestVeto` with `veto_halts_loop` / `no_veto_when_directive_is_none`). #26/#27 also add `test_module_docstring_states_healthcare_boundary`-shaped boundary test. Every flag assertion `== ["<exact flag text>"]`. `stops_at_sibling_header` injects a `RECOMMENDATION:` line between the first flag block and the next flag header; asserts the first flag list is unchanged.
- **Metadata keys:** `<flag>_flags` (snake_case of each header) · `<domain>_checklist` · one summary field (200-char cap) · `disclaimer` · `ledger_summary`; veto adds `veto_reason` + `vetoed` + `first_draft` when vetoed.
- **Template frontmatter (block form — registry fix `c1a7414`):** each of the 4 templates carries valid `name` / `description` / `inputs:` block-sequence frontmatter. Author in block form; do NOT inline. 44 new templates must all discover (Task 12 `test_registry.py` gate: files-on-disk == discovered per domain).
- **PRODUCTION_GAPS docstring:** name the live source systems (generic categories) + the qualified-approver gate + the "never auto-submitted/-released" hard stop + the dedicated third-model auditor (ARIS §3.1), mirroring the skeleton's 5–6 numbered items.
- **Commit per workflow.** PowerShell inline `-m` only; no `&`, `>`, `<`, `|`, `&&` (use words; write "90 percent CI" not "90% CI" only IF a shell metachar appears — `%` is safe).

---

### Task 0: Extend the D-LIFESCI-3 tripwire module set

- [ ] In `tests/unit/test_lifesciences_no_brand_names.py`, extend `lifesci_modules` with the 11 new test filenames (each `.exists()`-guarded, so adding before the files exist is harmless):

```python
        "test_rems_design.py",
        "test_premarket_cybersecurity.py",
        "test_post_market_clinical_followup.py",
        "test_heor_dossier.py",
        "test_serialization_dscsa.py",
        "test_biosimilar_comparability.py",
        "test_sterility_assurance.py",
        "test_cold_chain_excursion.py",
        "test_bioequivalence.py",
        "test_medical_information_response.py",
        "test_ccds_label_change.py",
```

- [ ] `python -m pytest tests/unit/test_lifesciences_no_brand_names.py -q` → PASS (new names skip; files absent).
- [ ] Commit: `test(lifesciences): register 11 Phase-2 batch-B test modules in D-LIFESCI-3 tripwire`

---

## No-veto workflows (clone `design_control_traceability.py`)

### Task 1: #18 REMSDesignWorkflow (no-veto · Pharma)
- Module `rems_design.py` · test `test_rems_design.py` · prefix `rems` · class `REMSDesignWorkflow` · Request `REMSDesignRequest` · threshold **7.5**.
- Owner `[OWNER: REMS / Risk Management Lead]` · summary field `product_description`.
- **8 fields:** `product_description` (product category + serious risk), `serious_risks`, `rems_goals`, `rems_elements` (Med Guide / communication plan / ETASU), `etasu_summary`, `implementation_system`, `assessment_plan`, `burden_assessment`.
- **Headers:** `RISK-MITIGATION FLAGS:` (a REMS element not matched to the serious risk it mitigates, or a risk with no mitigating element) · `BURDEN FLAGS:` (an element imposing disproportionate patient-access/provider burden vs the risk) · `ASSESSMENT-PLAN FLAGS:` (assessment metrics/timetable inadequate to show the REMS meets its goals).
- **5-dim:** 1 RISK-TO-ELEMENT FIT (30 → RISK-MITIGATION) · 2 ACCESS-BURDEN PROPORTIONALITY (25 → BURDEN) · 3 ASSESSMENT ADEQUACY (20 → ASSESSMENT-PLAN) · 4 IMPLEMENTATION FEASIBILITY (15) · 5 ACTIONABILITY (10).
- **PRODUCTION_GAPS:** REMS document-management + FDA submission system; ETASU implementation infrastructure (prescriber/pharmacy certification registry); patient-registry system; REMS assessment analytics; RA/Risk-Management approver gate (never an auto-submitted REMS); third-model auditor.
- **Example:** a long-acting opioid REMS with a prescriber-training element + patient Med Guide, whose assessment plan lacks a metric tied to reduction in the targeted overdose risk.
- **Test flag:** `ASSESSMENT-PLAN FLAGS:\n- No metric links REMS assessment to the reduction in the targeted overdose risk` → `metadata["assessment_plan_flags"] == [...]`.
- [ ] module → test → example + 4 templates → `pytest tests/unit/test_rems_design.py -q` PASS → commit `feat(lifesciences): add REMSDesignWorkflow (no-veto, REMS risk-to-element fit) [#18]`

### Task 2: #20 PremarketCybersecurityWorkflow (no-veto · Devices)
- Module `premarket_cybersecurity.py` · test `test_premarket_cybersecurity.py` · prefix `cybersec` · class `PremarketCybersecurityWorkflow` · Request `PremarketCybersecurityRequest` · threshold **7.5**.
- Owner `[OWNER: Product Security / Regulatory]` · summary field `device_description`.
- **8 fields:** `device_description` (connected device category + interfaces), `intended_use_environment`, `threat_model_summary`, `security_controls`, `sbom_summary`, `vulnerability_assessment`, `patchability_plan`, `residual_risk_summary` (residual cyber risk to safety/essential performance).
- **Headers:** `THREAT-MODEL FLAGS:` (an attack surface / threat not addressed by a control) · `SBOM-GAP FLAGS:` (a third-party/OSS component missing from the SBOM, or a component with an unresolved known vulnerability) · `PATCHABILITY FLAGS:` (no field-update path for a component that will need security patches over the device lifecycle).
- **5-dim:** 1 THREAT-MODEL COMPLETENESS (30 → THREAT-MODEL) · 2 SBOM & VULNERABILITY MANAGEMENT (25 → SBOM-GAP) · 3 PATCHABILITY / LIFECYCLE (20 → PATCHABILITY) · 4 SECURITY-CONTROL ADEQUACY (15) · 5 ACTIONABILITY (10).
- **PRODUCTION_GAPS:** threat-modeling tool; SBOM-generation + vulnerability-scanning pipeline; secure-update / PKI infrastructure; premarket-submission cybersecurity documentation system; product-security approver gate (never an auto-submitted cybersecurity package); third-model auditor.
- **Example:** a network-connected infusion pump whose SBOM omitted an embedded TLS library carrying a known CVE, and whose over-the-air update path covered the app but not the pump firmware.
- **Test flag:** `SBOM-GAP FLAGS:\n- Embedded TLS library with a known CVE is absent from the SBOM` → `metadata["sbom_gap_flags"] == [...]`.
- [ ] module → test → example + 4 templates → PASS → commit `feat(lifesciences): add PremarketCybersecurityWorkflow (no-veto, device threat-model/SBOM) [#20]`

### Task 3: #21 PostMarketClinicalFollowupWorkflow (no-veto · Devices)
- Module `post_market_clinical_followup.py` · test `test_post_market_clinical_followup.py` · prefix `pmcf` · class `PostMarketClinicalFollowupWorkflow` · Request `PMCFRequest` · threshold **7.5**.
- Owner `[OWNER: Clinical Affairs / Post-Market Surveillance]` · summary field `device_description`.
- **8 fields:** `device_description` (device category + indication), `clinical_evidence_baseline`, `pmcf_objectives`, `pmcf_methods` (studies / registries / literature / RWD), `residual_risks`, `benefit_risk_baseline`, `data_collected_summary`, `pms_linkage`.
- **Headers:** `EVIDENCE-GAP FLAGS:` (a claimed clinical benefit/indication with insufficient post-market evidence) · `RESIDUAL-RISK FLAGS:` (a residual risk not covered by a PMCF activity) · `PMCF-ADEQUACY FLAGS:` (a PMCF method inadequate to answer its stated objective / detect the risk).
- **5-dim:** 1 EVIDENCE SUFFICIENCY (30 → EVIDENCE-GAP) · 2 RESIDUAL-RISK COVERAGE (25 → RESIDUAL-RISK) · 3 PMCF-METHOD ADEQUACY (20 → PMCF-ADEQUACY) · 4 BENEFIT-RISK / PMS INTEGRATION (15) · 5 ACTIONABILITY (10).
- **PRODUCTION_GAPS:** clinical-evidence + literature-management system; PMCF study/registry data platform; PMS/PSUR system; risk-management-file integration; clinical-affairs approver gate (never an auto-filed PMCF evaluation); third-model auditor.
- **Example:** a hip implant whose PMCF plan relied only on complaint data for a long-term wear residual risk, with no registry or study capturing revision rates.
- **Test flag:** `PMCF-ADEQUACY FLAGS:\n- Complaint data alone cannot detect the long-term wear revision-rate risk` → `metadata["pmcf_adequacy_flags"] == [...]`.
- [ ] module → test → example + 4 templates → PASS → commit `feat(lifesciences): add PostMarketClinicalFollowupWorkflow (no-veto, PMCF adequacy) [#21]`

### Task 4: #22 HEORDossierWorkflow (no-veto · Cross)
- Module `heor_dossier.py` · test `test_heor_dossier.py` · prefix `heor` · class `HEORDossierWorkflow` · Request `HEORDossierRequest` · threshold **7.5**.
- Owner `[OWNER: HEOR / Market Access]` · summary field `product_description`.
- **8 fields:** `product_description` (product + indication), `value_proposition`, `comparators`, `clinical_evidence_summary`, `economic_model_summary`, `endpoints_used` (final vs surrogate), `extrapolation_assumptions`, `target_audience` (payer / HTA body / formulary committee).
- **Headers:** `COMPARATOR FLAGS:` (an inappropriate or missing comparator for the decision problem/market) · `ENDPOINT-RELEVANCE FLAGS:` (a surrogate/intermediate endpoint used where a patient-relevant final endpoint is required, without justification) · `EXTRAPOLATION FLAGS:` (a model extrapolation/assumption not supported by evidence or over-optimistic).
- **5-dim:** 1 COMPARATOR APPROPRIATENESS (30 → COMPARATOR) · 2 ENDPOINT RELEVANCE (25 → ENDPOINT-RELEVANCE) · 3 EXTRAPOLATION VALIDITY (20 → EXTRAPOLATION) · 4 MODEL TRANSPARENCY / EVIDENCE FIT (15) · 5 ACTIONABILITY (10).
- **PRODUCTION_GAPS:** evidence-synthesis / systematic-review platform; health-economic modeling software; HTA-submission templates + payer value-dossier system; real-world-evidence data sources; HEOR/market-access approver gate (never an auto-submitted value dossier); third-model auditor.
- **Example:** an oncology-therapy value dossier using progression-free survival to drive a lifetime cost-effectiveness model with optimistic survival extrapolation, against a comparator no longer standard of care.
- **Test flag:** `COMPARATOR FLAGS:\n- The chosen comparator is no longer standard of care in the target market` → `metadata["comparator_flags"] == [...]`.
- [ ] module → test → example + 4 templates → PASS → commit `feat(lifesciences): add HEORDossierWorkflow (no-veto, value-dossier comparator/endpoint) [#22]`

### Task 5: #24 SerializationDSCSAWorkflow (no-veto · Pharma)
- Module `serialization_dscsa.py` · test `test_serialization_dscsa.py` · prefix `serialization` · class `SerializationDSCSAWorkflow` · Request `SerializationDSCSARequest` · threshold **7.5**.
- Owner `[OWNER: Serialization / Supply-Chain Compliance]` · summary field `product_description`.
- **8 fields:** `product_description` (product category + packaging levels), `serialization_scheme` (GTIN + serial + lot + expiry; 2D DataMatrix), `aggregation_summary` (parent-child across item/case/pallet), `epcis_events` (commissioning/packing/shipping capture), `trading_partner_exchange`, `verification_process` (product-identifier verification for suspect/returned product), `saleable_returns_process`, `interoperability_status` (unit-level traceability readiness).
- **Headers:** `AGGREGATION FLAGS:` (a broken or missing parent-child aggregation link across packaging tiers) · `TRACEABILITY FLAGS:` (a required EPCIS event / trading-partner data element missing, breaking unit-level traceability) · `SALEABLE-RETURN FLAGS:` (a saleable return processed without the required product-identifier verification).
- **5-dim:** 1 AGGREGATION INTEGRITY (30 → AGGREGATION) · 2 EVENT / TRACEABILITY COVERAGE (25 → TRACEABILITY) · 3 SALEABLE-RETURN VERIFICATION (20 → SALEABLE-RETURN) · 4 INTEROPERABILITY READINESS (15) · 5 ACTIONABILITY (10).
- **PRODUCTION_GAPS:** serialization / L4 system; EPCIS repository + trading-partner exchange gateway; verification-router service; packaging-line aggregation capture; supply-chain-compliance approver gate (never an auto-certified DSCSA compliance record); third-model auditor.
- **Example:** a solid-dose product whose case-to-pallet aggregation was captured but item-to-case links were missing for a repackaged lot, and whose saleable-returns step verified lot but not the unit-level serial.
- **Test flag:** `AGGREGATION FLAGS:\n- Item-to-case aggregation links are missing for the repackaged lot` → `metadata["aggregation_flags"] == [...]`.
- [ ] module → test → example + 4 templates → PASS → commit `feat(lifesciences): add SerializationDSCSAWorkflow (no-veto, DSCSA aggregation/traceability) [#24]`

---

## Veto workflows (clone `batch_release_deviation.py`; DELETE the L-HEALTH-1 PHI caveat unless noted)

### Task 6: #17 BiosimilarComparabilityWorkflow (veto · Pharma)
- Module `biosimilar_comparability.py` · test `test_biosimilar_comparability.py` · prefix `biosimilar` · class `BiosimilarComparabilityWorkflow` · Request `BiosimilarComparabilityRequest` · threshold **8.0** · **veto**. DELETE PHI caveat.
- Owner `[OWNER: Biosimilar Development / Regulatory Affairs]` · summary field `product_description`.
- **8 fields:** `product_description` (proposed biosimilar + reference-product category), `analytical_similarity_summary`, `quality_attributes` (CQAs + tiering), `pk_pd_summary`, `clinical_comparability_summary` (comparative clinical/immunogenicity), `residual_uncertainty`, `bridging_summary`, `extrapolation_indications`.
- **Headers:** `ANALYTICAL-SIMILARITY FLAGS:` (a critical quality attribute not demonstrated analytically similar to the reference) · `RESIDUAL-UNCERTAINTY FLAGS:` (residual uncertainty understated / not resolved by the totality of evidence) · `BRIDGING FLAGS:` (a bridging or extrapolation step not justified by the comparability data).
- **5-dim:** 1 ANALYTICAL SIMILARITY (30 → ANALYTICAL-SIMILARITY) · 2 RESIDUAL-UNCERTAINTY RESOLUTION (25 → RESIDUAL-UNCERTAINTY) · 3 BRIDGING & EXTRAPOLATION (20 → BRIDGING) · 4 TOTALITY-OF-EVIDENCE COHERENCE (15) · 5 ACTIONABILITY (10).
- **VETO trigger:** a biosimilarity conclusion (or indication extrapolation) asserted where a CQA is NOT analytically similar and residual uncertainty is unresolved — claiming biosimilarity the data do not support. Banner: escalate to Regulatory Affairs; biosimilarity must not be concluded until the analytical-similarity gap and residual uncertainty are resolved.
- **PRODUCTION_GAPS:** analytical-characterization data systems (structural/functional assays); comparative-study data management; quality-attribute risk-ranking framework; regulatory comparability-dossier system; RA approver gate (never an auto-concluded biosimilarity determination); third-model auditor.
- **Example:** a proposed biosimilar mAb where a glycosylation CQA fell outside the reference range and the caller concluded biosimilarity while extrapolating to all indications.
- **Test flag (non-veto):** `ANALYTICAL-SIMILARITY FLAGS:\n- Glycosylation attribute falls outside the reference product range` → `metadata["analytical_similarity_flags"] == [...]`. **Veto:** `REVIEWER VETO: A biosimilarity conclusion is asserted while a glycosylation critical quality attribute is not analytically similar and the residual uncertainty is unresolved; biosimilarity must not be concluded. Escalate to Regulatory Affairs.` → `metadata["vetoed"] is True`.
- [ ] module (delete PHI caveat) → veto test → example + 4 templates → PASS → commit `feat(lifesciences): add BiosimilarComparabilityWorkflow (veto, analytical similarity) [#17]`

### Task 7: #19 SterilityAssuranceWorkflow (veto · Devices)
- Module `sterility_assurance.py` · test `test_sterility_assurance.py` · prefix `sterility` · class `SterilityAssuranceWorkflow` · Request `SterilityAssuranceRequest` · threshold **8.0** · **veto**. DELETE PHI caveat.
- Owner `[OWNER: Sterilization / Microbiology Quality]` · summary field `product_description`.
- **8 fields:** `product_description` (sterile device category + material/packaging), `sterilization_method` (EO / radiation / steam + rationale), `sal_target` (e.g. 10^-6), `bioburden_summary`, `validation_summary` (half-cycle/dose-setting/overkill evidence), `packaging_barrier`, `routine_control_summary` (BIs/dosimetry), `revalidation_status`.
- **Headers:** `SAL FLAGS:` (the claimed sterility assurance level not demonstrated by the validation/routine data) · `BIOBURDEN FLAGS:` (bioburden trending above the validated limit, or monitoring inadequate to support the cycle) · `VALIDATION-GAP FLAGS:` (a sterilization-validation or sterile-barrier element missing/expired for the claimed SAL).
- **5-dim:** 1 SAL DEMONSTRATION (30 → SAL) · 2 BIOBURDEN CONTROL (25 → BIOBURDEN) · 3 VALIDATION COMPLETENESS (20 → VALIDATION-GAP) · 4 ROUTINE-CONTROL / REVALIDATION RIGOR (15) · 5 ACTIONABILITY (10).
- **VETO trigger:** a sterility-assurance / product-release conclusion asserted where the claimed SAL is NOT demonstrated (validation gap, or bioburden above the validated limit) — releasing product as sterile without demonstrated sterility assurance. Banner: escalate to Microbiology Quality; product must not be released as sterile until the SAL is demonstrated.
- **PRODUCTION_GAPS:** sterilization-validation records system; bioburden / environmental-monitoring LIMS; dosimetry / BI release system; sterile-barrier packaging-validation records; microbiology-quality approver gate (never an auto-certified sterility release); third-model auditor.
- **Example:** an EO-sterilized single-use device where routine bioburden trended above the validated limit and the half-cycle validation predated a material change, while product was proposed for release at SAL 10^-6.
- **Test flag (non-veto):** `BIOBURDEN FLAGS:\n- Routine bioburden trending above the validated limit for the EO cycle` → `metadata["bioburden_flags"] == [...]`. **Veto:** `REVIEWER VETO: Product is proposed for release as sterile while the claimed SAL is not demonstrated and bioburden exceeds the validated limit; it must not be released as sterile. Escalate to Microbiology Quality.` → `metadata["vetoed"] is True`.
- [ ] module (delete PHI caveat) → veto test → example + 4 templates → PASS → commit `feat(lifesciences): add SterilityAssuranceWorkflow (veto, SAL demonstration) [#19]`

### Task 8: #23 ColdChainExcursionWorkflow (veto · Pharma/Diagnostics)
- Module `cold_chain_excursion.py` · test `test_cold_chain_excursion.py` · prefix `coldchain` · class `ColdChainExcursionWorkflow` · Request `ColdChainExcursionRequest` · threshold **8.0** · **veto**. DELETE PHI caveat.
- Owner `[OWNER: Quality / Cold-Chain Disposition]` · summary field `product_description`.
- **8 fields:** `product_description` (temperature-sensitive product category + label storage condition), `excursion_description` (temperature/duration/where in the chain), `label_storage_condition`, `stability_budget_summary` (stability data / MKT budget + allowable excursion time), `excursion_extent` (cumulative time-out-of-range vs remaining budget), `affected_units` (lots/quantities + scope), `impact_on_quality`, `proposed_disposition` (release / quarantine / reject).
- **Headers:** `STABILITY-IMPACT FLAGS:` (excursion impact on potency/stability not supported by stability data / MKT budget) · `DISPOSITION FLAGS:` (a proposed disposition inconsistent with the stability-budget conclusion) · `EXCURSION-SCOPE FLAGS:` (affected units / cumulative-excursion scope understated or incompletely traced).
- **5-dim:** 1 STABILITY-DATA JUSTIFICATION (30 → STABILITY-IMPACT) · 2 DISPOSITION CONSISTENCY (25 → DISPOSITION) · 3 EXCURSION-SCOPE COMPLETENESS (20 → EXCURSION-SCOPE) · 4 MKT / BUDGET RIGOR (15) · 5 ACTIONABILITY (10).
- **VETO trigger:** a `release` disposition for product whose cumulative excursion exceeds the stability budget (or has no supporting stability data) — releasing product whose quality is not assured after the excursion. Banner: escalate to Quality; the affected product must not be released until stability impact is resolved.
- **PRODUCTION_GAPS:** temperature-monitoring / data-logger system; stability database + MKT budget engine; batch/lot traceability system; deviation/disposition system; quality approver gate (never an auto-release after an excursion); third-model auditor.
- **Example:** a refrigerated biologic that spent cumulative hours above its labeled 2–8 °C range exceeding its documented excursion budget, proposed for release citing "brief excursion".
- **Test flag (non-veto):** `EXCURSION-SCOPE FLAGS:\n- Cumulative time-out-of-range across two legs not summed for the affected lots` → `metadata["excursion_scope_flags"] == [...]`. **Veto:** `REVIEWER VETO: A release is proposed for product whose cumulative excursion exceeds its stability budget with no supporting data; it must not be released. Escalate to Quality.` → `metadata["vetoed"] is True`.
- [ ] module (delete PHI caveat) → veto test → example + 4 templates → PASS → commit `feat(lifesciences): add ColdChainExcursionWorkflow (veto, excursion disposition) [#23]`

### Task 9: #25 BioequivalenceWorkflow (veto · Pharma)
- Module `bioequivalence.py` · test `test_bioequivalence.py` · prefix `bioequivalence` · class `BioequivalenceWorkflow` · Request `BioequivalenceRequest` · threshold **8.0** · **veto**. DELETE PHI caveat.
- Owner `[OWNER: Clinical Pharmacology / Regulatory]` · summary field `product_description`.
- **8 fields:** `product_description` (test vs reference product category + form), `study_design` (crossover/parallel, fasting/fed, single/multiple dose), `pk_parameters` (Cmax, AUC + 90 percent CI vs 80.00–125.00 percent limits), `study_population`, `statistical_analysis` (ANOVA, intra-subject CV, replicate design), `boundary_results` (whether any 90 percent CI touches/crosses a limit), `biowaiver_basis`, `special_considerations` (narrow-therapeutic-index / highly-variable drug).
- **Headers:** `PK-BOUNDARY FLAGS:` (a PK parameter's 90 percent CI outside the bioequivalence limits treated as equivalent) · `STUDY-DESIGN FLAGS:` (a design element — condition, dosing, population — inappropriate to establish bioequivalence for this product) · `WAIVER-JUSTIFICATION FLAGS:` (a biowaiver / narrowed-limit claim not justified by the applicable criteria).
- **5-dim:** 1 PK-BOUNDARY CONFORMANCE (30 → PK-BOUNDARY) · 2 STUDY-DESIGN VALIDITY (25 → STUDY-DESIGN) · 3 WAIVER / LIMIT JUSTIFICATION (20 → WAIVER-JUSTIFICATION) · 4 STATISTICAL RIGOR (15) · 5 ACTIONABILITY (10).
- **VETO trigger:** a bioequivalence conclusion asserted where a PK parameter's 90 percent CI falls outside the applicable limits (or a required study / tightened limit is absent) — declaring bioequivalence the data do not support. Banner: escalate to Clinical Pharmacology / Regulatory; bioequivalence must not be concluded until the boundary failure is resolved.
- **PRODUCTION_GAPS:** clinical-pharmacology / PK-analysis system; bioanalytical LIMS; statistical bioequivalence-analysis software; regulatory-submission system; clin-pharm approver gate (never an auto-concluded bioequivalence determination); third-model auditor.
- **Example:** a generic modified-release tablet whose Cmax 90 percent CI upper bound reached 128 percent under fed conditions, concluded bioequivalent on the AUC result alone.
- **Test flag (non-veto):** `PK-BOUNDARY FLAGS:\n- Cmax 90 percent CI upper bound at 128 percent is outside the bioequivalence limits` → `metadata["pk_boundary_flags"] == [...]`. **Veto:** `REVIEWER VETO: Bioequivalence is concluded while the Cmax 90 percent confidence interval falls outside the accepted limits; it must not be concluded. Escalate to Clinical Pharmacology.` → `metadata["vetoed"] is True`.
- [ ] module (delete PHI caveat) → veto test → example + 4 templates → PASS → commit `feat(lifesciences): add BioequivalenceWorkflow (veto, PK boundary) [#25]`

---

## Judgment-veto workflows (build last; each has a boundary docstring + test)

### Task 10: #26 MedicalInformationResponseWorkflow (veto · Pharma) — boundary + KEEP PHI caveat
- Module `medical_information_response.py` · test `test_medical_information_response.py` · prefix `medinfo` · class `MedicalInformationResponseWorkflow` · Request `MedicalInfoRequest` · threshold **8.0** · **veto**. **KEEP the L-HEALTH-1 PHI caveat** (inquiry can quote a specific patient case). **ADD boundary docstring + test.**
- **Boundary (module + class docstring):** "BOUNDARY (D-LIFESCI-2): distinct from the lifesciences PromotionalOffLabelReviewWorkflow — that reviews PROACTIVE promotional material where off-label promotion is prohibited; this drafts a REACTIVE response to an unsolicited medical inquiry, where a truthful, balanced, non-promotional scientific exchange (including off-label information) is permitted." Test: `doc = mod.__doc__.lower(); assert "distinct from" in doc and "promotionalofflabelreview" in doc.replace(" ", "")`.
- Owner `[OWNER: Medical Information / Medical Affairs]` · summary field `product_description`.
- **8 fields:** `product_description` (product category), `inquiry_summary` (the unsolicited question — may reference a specific case), `inquiry_source` (HCP / patient / unsolicited channel), `on_off_label_status`, `proposed_response`, `evidence_cited`, `balance_summary` (risks/limitations presented alongside efficacy), `promotional_review_status`.
- **Headers:** `OFF-LABEL FLAGS:` (an off-label statement exceeding a truthful, non-promotional, evidence-based answer to the specific unsolicited question — i.e. crosses into promotion) · `BALANCE FLAGS:` (efficacy presented without fair balance of risk/limitation) · `EVIDENCE-LEVEL FLAGS:` (a claim stated more strongly than its evidence level supports).
- **5-dim:** 1 OFF-LABEL BOUNDARY (30 → OFF-LABEL) · 2 FAIR BALANCE (25 → BALANCE) · 3 EVIDENCE CALIBRATION (20 → EVIDENCE-LEVEL) · 4 RESPONSIVENESS / NON-PROMOTIONAL TONE (15) · 5 ACTIONABILITY (10).
- **VETO trigger:** a response that crosses from a truthful, balanced, reactive scientific exchange into PROMOTION of an off-label use (proactive off-label promotion) — content a medical-information response must not send because it promotes an unapproved use. Banner: escalate to Medical Affairs / MLR; the response must not be sent as drafted because it promotes an off-label use.
- **PRODUCTION_GAPS:** medical-information management system + standard-response-document library; literature database; MLR review system; adverse-event intake integration (inquiries can contain AEs — must be routed to PV); medical-affairs approver gate (never an auto-sent medical-information response); third-model auditor.
- **Example:** an unsolicited HCP question about an off-label pediatric dose of an approved product, where the drafted response recommended the off-label regimen rather than neutrally summarizing the available evidence and its limitations.
- **Test flag (non-veto):** `BALANCE FLAGS:\n- Efficacy summary omits the known hepatic risk and monitoring requirement` → `metadata["balance_flags"] == [...]`. **Veto:** `REVIEWER VETO: The drafted response recommends an off-label pediatric regimen rather than neutrally summarizing the evidence; it promotes an unapproved use and must not be sent. Escalate to Medical Affairs.` → `metadata["vetoed"] is True`. + boundary test.
- [ ] module (keep PHI caveat + boundary) → veto test (+ boundary test) → example + 4 templates → PASS → commit `feat(lifesciences): add MedicalInformationResponseWorkflow (veto, off-label boundary; distinct from promotional review) [#26]`

### Task 11: #27 CCDSLabelChangeWorkflow (veto · Pharma) — boundary + DELETE PHI caveat
- Module `ccds_label_change.py` · test `test_ccds_label_change.py` · prefix `ccds` · class `CCDSLabelChangeWorkflow` · Request `CCDSLabelChangeRequest` · threshold **8.0** · **veto**. **DELETE PHI caveat** (aggregate input — summarized signal + label text, NOT raw case narratives). **ADD boundary docstring + test.**
- **Boundary (module + class docstring):** "BOUNDARY (D-LIFESCI-2): distinct from the lifesciences PharmacovigilanceSignalWorkflow — that detects and validates an aggregate safety SIGNAL and its labeling implication; this evaluates the downstream implementation of a Company Core Data Sheet (CCDS) safety label change across regions and the regulatory clock, given an already-established signal." Test: `doc = mod.__doc__.lower(); assert "distinct from" in doc and "pharmacovigilancesignal" in doc.replace(" ", "")`.
- Owner `[OWNER: Global Labeling / Regulatory Affairs]` · summary field `product_description`.
- **8 fields (aggregate/summarized — no raw case narratives):** `product_description` (product category), `safety_signal_summary` (the established/validated signal driving the change — summarized), `proposed_ccds_change` (proposed CCDS safety-section wording), `current_ccds_text`, `regional_label_status` (mapping to regional labels + divergence), `regulatory_timelines` (notification/submission clocks per region), `implementation_plan` (rollout + local-label updates), `benefit_risk_context` (population-level framing).
- **Headers:** `SAFETY-SIGNAL FLAGS:` (the proposed label change understates the established signal / a safety implication not reflected in the wording) · `REGIONAL-DIVERGENCE FLAGS:` (a region where the local label diverges from the CCDS change without justification, or a market missed) · `IMPLEMENTATION-CLOCK FLAGS:` (a regulatory notification/submission timeline the plan will miss).
- **5-dim:** 1 SIGNAL-TO-LABEL FIDELITY (30 → SAFETY-SIGNAL) · 2 REGIONAL CONSISTENCY (25 → REGIONAL-DIVERGENCE) · 3 TIMELINE COMPLIANCE (20 → IMPLEMENTATION-CLOCK) · 4 BENEFIT-RISK COHERENCE (15) · 5 ACTIONABILITY (10).
- **VETO trigger:** a CCDS/label-change plan that omits or materially understates an established serious safety signal in the safety labeling, OR misses a mandatory regulatory notification clock for a safety change — a labeling change that fails to communicate a known serious risk on time. Banner: escalate to Global Labeling / Regulatory Affairs; the label change must not proceed as drafted because it fails to convey the established serious risk / meet the safety-labeling clock.
- **PRODUCTION_GAPS:** global-labeling / CCDS management system; regulatory-submission tracking (per-region clocks); safety-signal-management system (upstream); local-label impact-assessment tooling; global-labeling approver gate (never an auto-implemented label change); third-model auditor.
- **Example:** an established serious hepatic risk requiring a CCDS warning where the proposed change downgraded it to a precaution and the rollout plan missed a region's expedited safety-labeling notification window.
- **Test flag (non-veto):** `REGIONAL-DIVERGENCE FLAGS:\n- One market's local label omits the new hepatic warning without a documented rationale` → `metadata["regional_divergence_flags"] == [...]`. **Veto:** `REVIEWER VETO: The proposed CCDS change downgrades an established serious hepatic risk to a precaution and misses a mandatory safety-labeling notification clock; it must not proceed as drafted. Escalate to Global Labeling.` → `metadata["vetoed"] is True`. + boundary test.
- [ ] module (delete PHI caveat + boundary) → veto test (+ boundary test) → example + 4 templates → PASS → commit `feat(lifesciences): add CCDSLabelChangeWorkflow (veto, safety-label fidelity; distinct from PV signal) [#27]`

---

### Task 12: Batch close — gate, ship-audit, docs refresh

- [ ] **Full local gate** (in order): `python -m ruff check .` · `python -m mypy src` · `python -m pytest tests/unit -q` · `python -m pytest tests/unit/test_lifesciences_no_brand_names.py -q` · `python -m pytest tests/unit/test_registry.py -q`. Expected: ruff clean; mypy strict clean; all tests pass (record the ACTUAL count from output — 1068 + ~11 workflows × ~8 ≈ ~1156, do not hardcode); tripwire green with 11 new modules scanned; registry files-on-disk == discovered (256 templates). Never push red.
- [ ] **Domain-ship security-audit subagent** (independent `general-purpose`, briefed blind) on the 11 new modules + tests. Brief: verify per module — (a) 5 review dims map onto exactly the 3 declared flag headers + 2 quality dims; (b) `score_threshold` matches idiom (8.0 veto / 7.5 no-veto) in BOTH criteria string and test `make_config`; (c) veto trigger domain-correct + audit-write-before-veto-check ordering intact; (d) shared-helper inheritance (M-PC-1 veto marker, H-IND-1 sibling-stop, L-PC-5 display cap) unbroken; (e) L-HEALTH-1 PHI caveat present ONLY on #26, absent on #17/#19/#23/#25/#27; (f) boundary docstring on #26 (vs promotional-off-label) + #27 (vs PV-signal); (g) no brand/company names; (h) input-shape injection vector specific to these request fields. Severity-tag + verdict. Fix CRIT/HIGH pre-push; fold LOW or log to gaps.
- [ ] **Docs refresh:** append **D-LIFESCI-6** to `decisions.md` (batch B built; catalog 27/27 complete). Mark #17–27 BUILT in the design-doc Phase-2 table. Counts everywhere (CLAUDE.md + README + architecture + deployment-architecture): workflows **52 → 63**, lifesciences "16 of 27" → "**27 of 27 (catalog complete)**", skill templates **212 → 256**, library test count → actual `pytest -q` number. Update `NEXT_SESSION.md` top banner + `production-readiness-gaps.md` §Lifesciences Phase-2 batch B (gate + audit verdict; retire the batch-B backlog block).
- [ ] **Docs commit** `[skip ci]`: `docs(lifesciences): mark Phase-2 batch B (#17-27) shipped; catalog complete; refresh counts, decisions, bookmark, gaps [skip ci]`
- [ ] **Push** (only if gate green AND no unresolved CRIT/HIGH): `git push origin main`.

---

## Self-Review

**1. Spec coverage:** design-doc rows #17–27 → Tasks 1–11 (build order: 5 no-veto → 4 veto → 2 judgment-veto). Tripwire → Task 0. Wiring → none needed (additive; pyproject glob + MCP domain cover lifesciences; `__init__` export-free; no count-pinning test but the tripwire set + registry). Docs/decisions/audit → Task 12.

**2. Placeholder scan:** none — each task names the clone-source, 8 fields, 3 headers, 5 weighted dims, owner, PRODUCTION_GAPS, generic example, exact `== [...]` flag assertion, and (veto) the verbatim veto directive.

**3. Consistency:** module ↔ test ↔ example ↔ template-prefix ↔ class ↔ Request ↔ metadata-key aligned per task; all 33 flag headers uppercase+space+hyphen (H-IND-1 safe, NO `_internal.py` change); thresholds 8.0 veto / 7.5 no-veto in both criteria string and test; PHI-caveat matrix (KEEP #26 only) and boundary (#26 + #27) stated once in shared conventions and echoed in the affected tasks.
