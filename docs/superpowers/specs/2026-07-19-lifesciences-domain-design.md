# Lifesciences Domain — Design Doc

**Date:** 2026-07-19
**Status:** DESIGN APPROVED — MVP-8 design approved; implementation pending
**Lineage:** 7th domain. Inherits the locked no-base-class recipe (D-RETAIL-7 → D-IND-1 → D-HEALTH-1).

---

## Why lifesciences fits the ARIS pattern

Regulated medical-product decisions are the textbook adversarial-collaboration case: a knowledgeable author (executor) has a structural incentive to reach a favorable, ship-it conclusion — the predicate *is* substantially equivalent, the assay *does* hit the sensitivity claim, the complaint *is* non-reportable, the promo claim *is* on-label — and a single-model author will confabulate a plausible regulatory rationale for the answer the business wants. The failure mode is not hallucinated facts; it is **motivated under-classification**: the cheaper, faster, less-restrictive regulatory call, argued convincingly.

A cross-model reviewer with no stake in the submission is positioned to catch exactly this: predicate stretch that forces a PMA, a performance claim the study n cannot support, a reportable event coded non-reportable, an off-label claim dressed as fair balance. The reviewer-veto pattern maps cleanly onto the regulatory-integrity subset, where a fundamentally-unsupportable output should be halted, not merely flagged.

This is the manufacturer's regulatory-affairs / quality desk — **not** the clinic and **not** the general factory floor (see boundary below).

## Domain identity + boundary

The archetype is a **diversified medical-products company** spanning four segments: in-vitro **diagnostics**, **medical devices**, branded/established **pharmaceuticals**, and **nutrition**. The intended user is a regulatory-affairs specialist, quality engineer, MLR reviewer, or post-market surveillance officer at the *manufacturer*.

Boundary vs the two adjacent shipped domains:

| Domain | User | Decision shape |
|--------|------|----------------|
| `healthcare` | Provider / payer / clinician | Clinical care, coverage, coding — patient-facing |
| `industrial` | General OEM / plant | Manufacturing ops, general quality, general recall |
| **`lifesciences`** | **Medical-product manufacturer RA/QA** | **FDA/EMA-regulated submission, labeling, reportability, field-action** |

Two MVP workflows sit adjacent to existing scenarios and are built as **distinct manufacturer-regulatory versions**, with the boundary stated in the module docstring — no shared code, different intended user, different decision:

- **#4 `DeviceReportabilityWorkflow`** vs healthcare `AdverseEventTriageWorkflow` — the latter grades clinical severity/causality for a provider; this decides the *manufacturer's* regulatory reportability (MDR / vigilance) and statutory clock.
- **#5 `FieldActionClassificationWorkflow`** vs industrial `RecallScopeManufacturingWorkflow` — the latter scopes a general product recall; this assigns an FDA medical-device recall **class (I/II/III)** and the 21 CFR 806 correction-vs-removal reportability call.

## Domain decisions (D-LIFESCI-1..4)

| # | Decision |
|---|----------|
| D-LIFESCI-1 | MVP-8 cut of a 27-workflow catalog; 19 Phase-2 designs locked in this doc for fill-in-not-redesign. Same no-domain-base-class rule as D-IND-1 (D-RETAIL-7 lineage). |
| D-LIFESCI-2 | Domain boundary: lifesciences = regulated medical-product **manufacturer** decisions. Workflows #4 + #5 are distinct manufacturer-regulatory versions of scenarios adjacent to `healthcare`/`industrial`; boundary stated in each module docstring; no shared code, no shared intended user. |
| D-LIFESCI-3 | **No brand or company names anywhere** — code, prompts, examples, tests. Generic product *categories* only (e.g. "a rapid antigen test", "a continuous glucose monitor", "a drug-eluting stent", "an adult nutritional shake"). Illustrative FDA regulatory citations (21 CFR parts) are scenario *context*, not legal advice. `_DISCLAIMER` states outputs are decision-support requiring qualified RA/QA sign-off — not a regulatory submission, and not legal or medical advice. |
| D-LIFESCI-4 | Reviewer-veto on the 5 halt-worthy regulatory-integrity workflows (#1 510(k) SE, #2 assay claim, #3 promo/off-label, #4 reportability, #5 field-action); no-veto on the 3 advisory-analysis workflows (#6 PMOA, #7 design-control, #8 nutrition). |

## Convention recap (inherited — verbatim from retail → pc → industrial → healthcare lineage)

1. `*Request` dataclass with `to_prompt_text()`; every free-text field capped at `_MAX_FIELD_CHARS = 1500`.
2. Sanitize all request text via `sanitize_for_prompt` at the workflow boundary (6000-char post-concat cap).
3. Loop up to `config.max_review_rounds`; convergence = `review.approved AND not current_flags AND not veto` (veto only for the 5 veto workflows).
4. `BaseWorkflow._register_claims` for every `## Claims` line (inherits the 200-claims/round cap).
5. `self.wiki.add_feedback` for every reviewer critique.
6. `extract_flags(critique, header)` for each flag class (shared helper — inherits M1 line-anchor + H-IND-1 sibling-stop + L2 cap).
7. `truncate_flag_display(flags)` in every `_format_flag_section`.
8. Veto workflows delegate to `core._internal.extract_veto_directive` (M-PC-1); include the L-PC-2 FORMAT NOTE in criteria.
9. `_build_*_checklist` returning human-action items; **approver role printed as the first line**.
10. `WorkflowResult` with `output` suffixed by `_DISCLAIMER` (injected in code, not prompt); `metadata` with per-class flag lists, checklist, `ledger_summary`, and (if veto) `veto_reason` + `first_draft`.
11. `PRODUCTION_GAPS` docstring naming the live integrations a real deployment requires.
12. Cite ARIS in the module docstring.

**Flag-header safety (H-IND-1):** every flag header below is uppercase letters + spaces + hyphens only — zero digit-containing or slash-containing headers. The shared `_is_sibling_header_lhs` regex covers all of them; no `core/_internal.py` change required. (Note: "510(k)" appears only in prose/criteria, never as a flag header.)

## Package structure

```
src/adv_multi_agent/lifesciences/
  __init__.py
  workflows/
    __init__.py
    substantial_equivalence_510k.py
    assay_performance_claim.py
    promotional_off_label_review.py
    device_reportability.py
    field_action_classification.py
    combination_product_pmoa.py
    design_control_traceability.py
    nutrition_health_claim.py
  skills/
    templates/            # one skill template per workflow (approver checklist + criteria)
examples/lifesciences/     # one runnable synthetic example per workflow
tests/unit/test_<workflow>.py
```

Plus: `pyproject.toml` `[tool.setuptools.package-data]` row for `lifesciences/skills/templates/*`; MCP `SKILLS_DOMAIN` registration of the string `"lifesciences"`; decision rows `D-LIFESCI-1..4` in `docs/decisions.md`.

---

## MVP-8 workflow specs

Legend: **[veto]** uses the reviewer-veto halt pattern. All gates additionally require `review.approved` and `not veto` where applicable.

### 1. `SubstantialEquivalence510kWorkflow` [veto] — Devices

Draft/critique the substantial-equivalence rationale for a 510(k). The executor argues the subject device is substantially equivalent to a cleared predicate; the reviewer flags predicate stretch that would draw a Not-Substantially-Equivalent finding or force a PMA / De Novo.

- **`SERequest` fields:** `subject_device_description`, `intended_use`, `indications_for_use`, `technological_characteristics`, `candidate_predicates` (name · product code · cleared intended use), `performance_data_summary`, `differences_from_predicate`, `prior_fda_interactions`.
- **Flag classes:**
  - `PREDICATE-MISMATCH FLAGS:` — predicate has a different intended use / device type; not a valid SE anchor.
  - `INDICATION-CREEP FLAGS:` — subject indications-for-use broader than the predicate's cleared indications.
  - `TECHNOLOGY-DELTA FLAGS:` — new technological characteristics raise new questions of safety/effectiveness (the NSE trigger).
- **Gate:** `approved AND zero PREDICATE-MISMATCH AND zero INDICATION-CREEP AND zero TECHNOLOGY-DELTA AND no veto`.
- **Veto trigger:** SE claim is fundamentally unsupportable (near-certain NSE; asserting it would misrepresent equivalence to FDA).
- **Approver:** Regulatory Affairs lead sign-off.
- **PRODUCTION_GAPS:** FDA 510(k) clearance database + product-classification database (21 CFR 862–892), eSTAR builder, prior-submission archive.

### 2. `AssayPerformanceClaimWorkflow` [veto] — Diagnostics

Review proposed analytical/clinical performance claims for an in-vitro diagnostic against the underlying study data. The executor drafts labeling claims; the reviewer flags claims the data do not support.

- **`AssayClaimRequest` fields:** `assay_description`, `intended_use`, `analyte_measurand`, `claim_set` (sensitivity, specificity, LoD, precision, linearity), `study_design_summary` (n · reference method · population), `interference_panel_tested`, `cross_reactivity_data`, `stability_claims`.
- **Flag classes:**
  - `SENSITIVITY-CLAIM FLAGS:` — clinical/analytical sensitivity claim exceeds what the study n / confidence interval supports.
  - `SPECIFICITY-CLAIM FLAGS:` — specificity / false-positive-rate claim overstated vs the data.
  - `INTERFERENCE FLAGS:` — interferents or cross-reactants untested for a claimed matrix / population.
- **Gate:** `approved AND zero of each AND no veto`.
- **Veto trigger:** a performance claim overstated enough to cause misdiagnosis risk / an adulteration-misbranding exposure.
- **Approver:** Diagnostics Regulatory + R&D sign-off.
- **PRODUCTION_GAPS:** LIMS, CLSI EP-protocol study data, clinical-study database, labeling-management system.

### 3. `PromotionalOffLabelReviewWorkflow` [veto] — Pharma / Device (MLR)

Medical-Legal-Regulatory review of promotional material against the approved label. The executor reviews/redlines promo copy; the reviewer flags off-label, fair-balance, and substantiation issues.

- **`PromoReviewRequest` fields:** `material_type` (visual aid · web · email · booth panel), `target_audience` (HCP / consumer), `promo_claims`, `approved_labeling_reference` (indications + limitations), `cited_references`, `risk_information_present`, `comparative_claims`.
- **Flag classes:**
  - `OFF-LABEL FLAGS:` — claim outside the approved indication / population / dosing.
  - `FAIR-BALANCE FLAGS:` — risk/limitation information absent or not comparably prominent to benefit claims.
  - `SUBSTANTIATION FLAGS:` — efficacy / comparative / superiority claim not backed by substantial evidence or an adequate head-to-head cite.
- **Gate:** `approved AND zero of each AND no veto`.
- **Veto trigger:** material would draw an enforcement/untitled letter (clear off-label promotion or omission of material risk).
- **Approver:** MLR committee (Medical + Legal + Regulatory) sign-off.
- **PRODUCTION_GAPS:** promotional-review DAM (e.g. Veeva Vault PromoMats), approved-labeling repository, claims/reference library.

### 4. `DeviceReportabilityWorkflow` [veto] — Devices (post-market)

Decide whether a device complaint/event is regulatory-reportable and on what timeline (manufacturer MDR / vigilance). The executor triages; the reviewer flags under-reporting. **Boundary:** distinct from healthcare `AdverseEventTriageWorkflow` (clinical severity/causality for a provider) — this is the manufacturer's regulatory reportability decision and statutory clock.

- **`ReportabilityRequest` fields:** `complaint_narrative`, `device_identifier` (UDI / model), `event_outcome` (death / serious injury / malfunction / no harm), `patient_impact`, `malfunction_recurrence_potential`, `prior_similar_events_count`, `market_regions`, `date_became_aware`.
- **Flag classes:**
  - `REPORTABILITY FLAGS:` — event meets a reporting definition but is coded non-reportable.
  - `SERIOUS-INJURY FLAGS:` — outcome under-graded (a reportable serious injury coded minor).
  - `MALFUNCTION-TREND FLAGS:` — a recurring malfunction crosses a trend/threshold reporting trigger the single event masks.
- **Gate:** `approved AND zero of each AND no veto`.
- **Veto trigger:** a "non-reportable" determination that is actually reportable under the applicable regulation (21 CFR 803 / regional vigilance).
- **Approver:** Post-market Surveillance / Vigilance officer sign-off.
- **PRODUCTION_GAPS:** complaint-handling system (e.g. TrackWise), FDA eMDR, EU EUDAMED vigilance, reportability decision-tree engine.

### 5. `FieldActionClassificationWorkflow` [veto] — Devices (post-market)

Scope and classify a field action (correction/removal): health-hazard evaluation, recall class, and reportability. The executor scopes; the reviewer flags under-scoping. **Boundary:** distinct from industrial `RecallScopeManufacturingWorkflow` (general product recall) — this assigns an FDA medical-device recall class and the 21 CFR 806 reportability call.

- **`FieldActionRequest` fields:** `problem_description`, `health_hazard_evaluation`, `affected_lots_serials`, `distribution_scope`, `action_type` (correction vs removal), `root_cause_summary`, `patient_exposure_estimate`, `prior_related_actions`.
- **Flag classes:**
  - `RECALL-CLASS FLAGS:` — proposed class under-graded vs the health hazard (Class II proposed where a reasonable probability of serious harm indicates Class I).
  - `CORRECTION-REMOVAL FLAGS:` — a 21 CFR 806 reportable correction/removal characterized as a non-reportable enhancement or stock recovery.
  - `HEALTH-HAZARD FLAGS:` — the health-hazard evaluation understates probability, severity, or affected population.
- **Gate:** `approved AND zero of each AND no veto`.
- **Veto trigger:** a recall-class downgrade or "not reportable" call that leaves patients exposed.
- **Approver:** Recall committee / Chief Quality Officer sign-off.
- **PRODUCTION_GAPS:** complaint/CAPA system, FDA Recall Enterprise System, health-hazard-evaluation board, UDI / lot-genealogy traceability.

### 6. `CombinationProductPMOAWorkflow` [no veto] — Cross-segment

Determine a combination product's primary mode of action → lead FDA center and regulatory pathway (21 CFR 3). The executor argues PMOA; the reviewer flags misrouting.

- **`PMOARequest` fields:** `product_description`, `constituent_parts` (drug / device / biologic), `therapeutic_effect_mechanism`, `each_constituent_contribution`, `proposed_pmoa`, `proposed_lead_center`, `precedent_products`.
- **Flag classes:**
  - `PMOA FLAGS:` — primary-mode-of-action determination inconsistent with the described therapeutic mechanism.
  - `LEAD-CENTER FLAGS:` — proposed lead center (CDER / CBER / CDRH) does not follow from the PMOA.
  - `PATHWAY FLAGS:` — proposed submission pathway (NDA / BLA / PMA / 510(k)) inconsistent with the center + PMOA.
- **Gate:** `approved AND zero of each` (advisory classification analysis — no veto).
- **Approver:** Regulatory strategy lead sign-off.
- **PRODUCTION_GAPS:** 21 CFR 3 + Office of Combination Products RFD-precedent database, jurisdictional-determination archive.

### 7. `DesignControlTraceabilityWorkflow` [no veto] — Devices

Audit a Design History File for design-control traceability (21 CFR 820.30 / ISO 13485). The executor summarizes traceability; the reviewer flags gaps.

- **`DesignControlRequest` fields:** `device_description`, `design_inputs` (requirements), `design_outputs` (specifications), `verification_evidence`, `validation_evidence`, `risk_analysis_reference` (ISO 14971), `design_review_records`, `trace_matrix_summary`.
- **Flag classes:**
  - `TRACE-GAP FLAGS:` — a design input with no linked output, or an output with no linked input.
  - `VERIFICATION FLAGS:` — a design output lacking verification evidence.
  - `VALIDATION FLAGS:` — a user-need lacking design-validation evidence (or V&V conflated).
- **Gate:** `approved AND zero of each` (gap-finding audit — no veto).
- **Approver:** Design Assurance / QE sign-off.
- **PRODUCTION_GAPS:** PLM (Windchill / Teamcenter), requirements management (DOORS), eQMS, ISO 14971 risk-management file.

### 8. `NutritionHealthClaimWorkflow` [no veto] — Nutrition

Review a nutrition product's label claims for substantiation and regulatory adequacy. The executor reviews claims; the reviewer flags unsubstantiated, inadequate, or allergen issues.

- **`NutritionClaimRequest` fields:** `product_category` (adult nutritional / infant formula / supplement), `claim_set` (structure-function · nutrient-content · health), `substantiation_dossier_summary`, `target_population`, `nutrient_profile`, `allergen_declaration`, `infant_formula_flag`.
- **Flag classes:**
  - `CLAIM-SUBSTANTIATION FLAGS:` — a structure-function claim lacking competent-reliable evidence / required notification, or a disease (health) claim made without authorization.
  - `NUTRIENT-ADEQUACY FLAGS:` — the nutrient profile is inadequate vs the applicable requirement (e.g. infant-formula nutrient minimums, 21 CFR 107).
  - `ALLERGEN FLAGS:` — an undeclared major allergen or a missing cross-contact statement.
- **Gate:** `approved AND zero of each` (no veto).
- **Approver:** Nutrition Regulatory + Scientific Affairs sign-off.
- **PRODUCTION_GAPS:** substantiation-dossier repository, structure-function-claim notification log, nutrient database, allergen-control plan.

---

## Phase-2 catalog (19 locked designs)

Recorded so a later build is fill-in, not re-design. Flag hints illustrative.

**Status:** #9–16 BUILT as **Phase-2 batch A** (2026-07-19; plan
[`2026-07-19-lifesciences-phase2-batch-a.md`](../plans/2026-07-19-lifesciences-phase2-batch-a.md)).
#17–27 (rows below) remain designed-not-built (batch B). The batch-A flag hints
became the real flag headers; the 4th quality dimension + veto trigger were
authored in the plan.

| # | Workflow | Segment | Flag hint | Veto |
|---|----------|---------|-----------|------|
| 9 | `GxPDataIntegrityWorkflow` | Cross | `ALCOA`, `AUDIT-TRAIL`, `ATTRIBUTION` | — |
| 10 | `ComputerSystemValidationWorkflow` | Cross | `INTENDED-USE`, `TRACE-GAP`, `TEST-EVIDENCE` | — |
| 11 | `StabilityShelfLifeWorkflow` | Pharma/Nutrition | `EXTRAPOLATION`, `TREND`, `SPEC-EXCEEDANCE` | — |
| 12 | `BatchReleaseDeviationWorkflow` | Pharma | `CRITICALITY`, `IMPACT-ASSESSMENT`, `RELEASE-RISK` | veto |
| 13 | `CMOQualificationWorkflow` | Cross | `GMP-GAP`, `DATA-INTEGRITY`, `CAPACITY` | — |
| 14 | `UDILabelingWorkflow` | Devices | `IDENTIFIER`, `GUDID-CONSISTENCY`, `PACKAGING-TIER` | — |
| 15 | `ClinicalProtocolDesignWorkflow` | Pharma/Device | `ENDPOINT`, `POWER`, `SAFETY-MONITORING` | veto |
| 16 | `PharmacovigilanceSignalWorkflow` | Pharma | `SIGNAL-STRENGTH`, `CAUSALITY`, `LABELING-IMPACT` | veto |
| 17 | `BiosimilarComparabilityWorkflow` | Pharma | `ANALYTICAL-SIMILARITY`, `RESIDUAL-UNCERTAINTY`, `BRIDGING` | veto |
| 18 | `REMSDesignWorkflow` | Pharma | `RISK-MITIGATION`, `BURDEN`, `ASSESSMENT-PLAN` | — |
| 19 | `SterilityAssuranceWorkflow` | Devices | `SAL`, `BIOBURDEN`, `VALIDATION-GAP` | veto |
| 20 | `PremarketCybersecurityWorkflow` | Devices | `THREAT-MODEL`, `SBOM-GAP`, `PATCHABILITY` | — |
| 21 | `PostMarketClinicalFollowupWorkflow` | Devices | `EVIDENCE-GAP`, `RESIDUAL-RISK`, `PMCF-ADEQUACY` | — |
| 22 | `HEORDossierWorkflow` | Cross | `COMPARATOR`, `ENDPOINT-RELEVANCE`, `EXTRAPOLATION` | — |
| 23 | `ColdChainExcursionWorkflow` | Pharma/Diagnostics | `STABILITY-IMPACT`, `DISPOSITION`, `EXCURSION-SCOPE` | veto |
| 24 | `SerializationDSCSAWorkflow` | Pharma | `AGGREGATION`, `TRACEABILITY`, `SALEABLE-RETURN` | — |
| 25 | `BioequivalenceWorkflow` | Pharma | `PK-BOUNDARY`, `STUDY-DESIGN`, `WAIVER-JUSTIFICATION` | veto |
| 26 | `MedicalInformationResponseWorkflow` | Pharma | `OFF-LABEL`, `BALANCE`, `EVIDENCE-LEVEL` | veto |
| 27 | `CCDSLabelChangeWorkflow` | Pharma | `SAFETY-SIGNAL`, `REGIONAL-DIVERGENCE`, `IMPLEMENTATION-CLOCK` | veto |

## Universal PRODUCTION_GAPS (all 8 workflows)

Every workflow's `PRODUCTION_GAPS` docstring states the domain-wide caveat: **these workflows are decision-support, not decision-making.** A real deployment requires (a) the named source systems as live integrations rather than caller-pasted text, (b) a qualified human approver whose role is printed as the checklist's first line, and (c) a hard stop that the LLM output is never auto-submitted to FDA / a notified body / EMA. Regulatory citations in prompts are scenario framing, not legal counsel.

## Build sequence (MVP-8)

Lowest-risk / most-observable convergence first; veto workflows after the no-veto ones prove the loop:

1. `DesignControlTraceabilityWorkflow` (#7, no veto, self-contained gap audit)
2. `NutritionHealthClaimWorkflow` (#8, no veto)
3. `CombinationProductPMOAWorkflow` (#6, no veto)
4. `AssayPerformanceClaimWorkflow` (#2, veto — first veto workflow)
5. `SubstantialEquivalence510kWorkflow` (#1, veto)
6. `PromotionalOffLabelReviewWorkflow` (#3, veto)
7. `DeviceReportabilityWorkflow` (#4, veto — validate the healthcare boundary here)
8. `FieldActionClassificationWorkflow` (#5, veto — validate the industrial boundary here)

Ship-audit after the sweep per the domain-ship cadence: focused `security-audit` subagent on the new surface; verify shared-helper inheritance (M-PC-1 / H-IND-1 / L-PC-5) and surface any input-shape attack vector specific to the regulatory request fields.

## Compliance / naming constraint (load-bearing)

No brand or company name appears in any artifact of this domain — code, prompt template, example, or test. Scenarios use generic product **categories**. The `_DISCLAIMER` (injected in code, per convention #10) reads as decision-support requiring qualified Regulatory Affairs / Quality Assurance sign-off, explicitly not a regulatory submission and not legal or medical advice.
