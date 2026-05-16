# Healthcare Domain — Design Doc

**Date:** 2026-05-16
**Author:** Giri Manchaiah
**Status:** IN PROGRESS — MVP-8 design approved; implementation pending
**Based on:** Yang, R., Li, Y., & Li, S. (2026). *ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration*. arXiv:2605.03042.

---

## Why healthcare fits the ARIS pattern

| Property | Healthcare manifestation |
|---|---|
| Irreversibility | Trial enrollment, treatment contraindication, adverse event report — each has patient-safety or regulatory consequence that cannot be undone |
| Bias risk | Clinical trial eligibility has documented demographic exclusion bias; cross-model reviewer is the safeguard (mirrors parole bias-gate pattern) |
| Regulator audit trail | FDA 21 CFR Part 11 / 312 (ADR reporting), CMS (prior auth, 21st Century Cures Act), HIPAA, IRB/ICH-GCP (trial eligibility) |
| Echo-chamber risk | Clinicians and payer reviewers develop precedent bias; same-family LLMs replicate it; cross-family reviewer is the structural safeguard |
| Veto class | Absolute contraindication, mandatory ADR report trigger, bad-faith prior auth denial — all warrant reviewer halt independent of score |

---

## Domain decisions (D-HEALTH-1..4)

| ID | Decision |
|---|---|
| D-HEALTH-1 | MVP-8 cut of 27-workflow catalog; 19 Phase-2 designs locked in this doc; same no-domain-base-class rule as D-IND-1 (D-RETAIL-7 lineage) |
| D-HEALTH-2 | Score threshold **8.0** for all 4 veto-using workflows (vs 7.5 elsewhere); justified by patient-safety and regulatory stakes |
| D-HEALTH-3 | All patient-identifying fields are caller-supplied free-text; PHI de-identification is **caller's responsibility**; every workflow docstring lists this as PRODUCTION_GAP #1 |
| D-HEALTH-4 | Veto trigger language in reviewer criteria templates references specific regulatory citations (FDA 7/15-day expedited report, ICH E2A, IRB exclusion criteria) — not generic "safety concern" phrasing |

---

## Convention recap (inherited from retail → pc → industrial lineage)

Every healthcare workflow MUST follow the domain-add convention (D-IND-1):

1. `*Request` dataclass with `to_prompt_text()` — all `str` fields, `_MAX_FIELD_CHARS = 1500` module constant, per-field `[:cap]` slice (or `cap_field()` for new-pattern warning).
2. `sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)` at the workflow boundary.
3. Loop up to `config.max_review_rounds`; convergence = `review.approved AND not current_flags AND not veto` (veto only for the 4 veto-using workflows).
4. `BaseWorkflow._register_claims` for every `## Claims` line.
5. `self.wiki.add_feedback` for every reviewer critique.
6. `extract_flags(critique, header)` for each flag class.
7. `truncate_flag_display(flags)` in every `_format_flag_section`.
8. `_build_*_checklist` returning human-action items; owner role printed as first line.
9. `WorkflowResult` with `output` suffixed by `_DISCLAIMER` (injected in code, not prompt), `metadata` including flag lists, checklist, `ledger_summary`, and (if veto) `veto_reason` + `first_draft`.
10. `PRODUCTION_GAPS` docstring naming required live integrations before any pilot deployment.
11. ARIS paper citation in module docstring.

Skill templates: `src/adv_multi_agent/healthcare/skills/templates/`, prefixed with scenario noun.
Examples: `examples/healthcare/<scenario>.py`, synthetic / de-identified data only.
Tests: `tests/unit/test_<workflow>.py`, ~8 tests each.

---

## Package structure

```
src/adv_multi_agent/healthcare/
    __init__.py
    workflows/
        __init__.py
        clinical_trial_eligibility.py   # [veto]
        treatment_plan_review.py        # [veto]
        drug_interaction_flagging.py    # [veto]
        adverse_event_triage.py         # [veto]
        prior_authorization_review.py
        claims_appeal_review.py
        diagnosis_code_audit.py
        discharge_planning_risk.py
    skills/
        __init__.py
        templates/
            trial_initial.md
            trial_revision.md
            trial_review.md
            trial_checklist.md
            treatment_initial.md
            treatment_revision.md
            treatment_review.md
            treatment_checklist.md
            drug_initial.md
            drug_revision.md
            drug_review.md
            drug_checklist.md
            adverse_initial.md
            adverse_revision.md
            adverse_review.md
            adverse_checklist.md
            prior_auth_initial.md
            prior_auth_revision.md
            prior_auth_review.md
            prior_auth_checklist.md
            claims_appeal_initial.md
            claims_appeal_revision.md
            claims_appeal_review.md
            claims_appeal_checklist.md
            diagnosis_initial.md
            diagnosis_revision.md
            diagnosis_review.md
            diagnosis_checklist.md
            discharge_initial.md
            discharge_revision.md
            discharge_review.md
            discharge_checklist.md
```

32 skill templates total (4 per workflow × 8 workflows).

---

## MVP-8 workflow specs

### 1. `ClinicalTrialEligibilityWorkflow` [veto]

**Decision class:** IRB-governed patient enrollment — irreversible once patient is enrolled or excluded; demographic bias is documented in trial enrollment literature.

**Request dataclass:** `TrialEligibilityRequest`
```
trial_id: str              # NCT number or sponsor trial ID
protocol_summary: str      # inclusion / exclusion criteria (caller-supplied from protocol)
patient_profile: str       # age, sex, diagnosis, comorbidities, functional status (de-identified)
biomarker_status: str      # relevant biomarker / lab values for eligibility
prior_treatments: str      # treatment history relevant to exclusion criteria
competing_risks: str       # conditions that may interact with investigational intervention
site_context: str          # enrollment site, sponsor, phase, arms
```

**Convergence gate:**
- Score ≥ 8.0
- AND zero BIAS FLAGS
- AND zero ELIGIBILITY FLAGS
- AND zero EVIDENCE FLAGS
- AND no REVIEWER VETO

**Veto triggers (reviewer criteria template):**
- Patient meets a life-threatening exclusion criterion (organ dysfunction, prohibited concomitant med, active infection per protocol) but draft marks eligible
- Protected-class attribute (race, sex, age, disability) appears to be a determinative exclusion factor without protocol-specified clinical justification
- Eligibility determination contradicts primary evidence in `protocol_summary` or `biomarker_status`

**Checklist owner:** IRB coordinator / principal investigator

**Score threshold:** 8.0

**PRODUCTION_GAPS:**
1. PHI de-identification — `patient_profile` is free-text; production requires integration with EHR de-identification pipeline (HIPAA Safe Harbor or Expert Determination)
2. Live protocol database — `protocol_summary` should be fetched from ClinicalTrials.gov API or sponsor EDC, not paraphrased by caller
3. Real-time eligibility check — biomarker status, lab values, and medication lists should be pulled from EHR (Epic, Cerner) at eligibility-check time
4. IRB sign-off gate — enrollment decision is IRB-governed; AI output is advisory; PI must confirm eligibility against primary protocol
5. Dedicated third-model bias auditor — production should run a separately configured auditor model whose only job is demographic-bias detection

---

### 2. `TreatmentPlanReviewWorkflow` [veto]

**Decision class:** Clinical prescribing — contraindicated treatment can cause irreversible patient harm.

**Request dataclass:** `TreatmentPlanRequest`
```
patient_summary: str          # age, weight, allergies, active diagnoses (de-identified)
proposed_plan: str            # medications, procedures, dosing, route, duration
current_medications: str      # full med list including OTC, supplements, herbals
lab_values: str               # relevant labs: renal (eGFR/CrCl), hepatic (LFTs), CBC, electrolytes
clinical_guidelines: str      # applicable guideline citations (caller-supplied)
contraindication_context: str # known drug/allergy/condition contraindications from patient record
```

**Convergence gate:**
- Score ≥ 8.0
- AND zero GUIDELINE FLAGS
- AND zero CONTRAINDICATION FLAGS
- AND zero RISK FLAGS
- AND no REVIEWER VETO

**Veto triggers:**
- Absolute drug-allergy contraindication present in `patient_summary` or `contraindication_context`
- Drug-organ failure contraindication (e.g. renally-cleared drug at full dose with eGFR < threshold per guidelines)
- Procedure listed in `proposed_plan` is contraindicated given documented comorbidity or medication

**Checklist owner:** Attending physician

**Score threshold:** 8.0

**PRODUCTION_GAPS:**
1. PHI de-identification — all fields are free-text; caller's responsibility
2. EHR integration — `current_medications`, `lab_values`, `contraindication_context` should be pulled from Epic/Cerner medication reconciliation and lab results
3. Live drug knowledge base — contraindication checking should be backed by Lexicomp, Micromedex, or First Datacheck, not caller-supplied text alone
4. Physician sign-off gate — no treatment plan may be implemented without attending physician review and order entry
5. Pharmacy verification — for medication changes, pharmacist must independently verify before dispensing

---

### 3. `DrugInteractionFlaggingWorkflow` [veto]

**Decision class:** Polypharmacy safety — absolute contraindications and life-threatening interactions are patient-safety irreversibles.

**Request dataclass:** `DrugInteractionRequest`
```
patient_id: str          # de-identified patient reference
medication_list: str     # current medications with doses, routes, frequencies
new_medication: str      # proposed addition: name, dose, route, indication
indication: str          # clinical reason for adding new_medication
renal_function: str      # eGFR or CrCl (affects clearance of many drugs)
hepatic_function: str    # Child-Pugh class or LFT values
allergy_history: str     # documented allergies and reaction severity
formulary_reference: str # caller-supplied formulary or interaction database excerpt
```

**Convergence gate:**
- Score ≥ 8.0
- AND zero SEVERITY FLAGS
- AND zero EVIDENCE FLAGS
- AND zero CONTRAINDICATION FLAGS
- AND no REVIEWER VETO

**Veto triggers:**
- Absolute contraindication between `new_medication` and any drug in `medication_list` (per formulary or standard reference)
- QTc-prolonging combination in patient with documented cardiac history or prolonged baseline QTc
- Narrow-therapeutic-index interaction (e.g. warfarin + NSAID, lithium + thiazide) with no dose adjustment plan
- Cross-allergy with documented allergy in `allergy_history`

**Checklist owner:** Clinical pharmacist

**Score threshold:** 8.0

**PRODUCTION_GAPS:**
1. PHI de-identification — all fields are free-text; caller's responsibility
2. Live interaction database — `formulary_reference` should be a real-time Lexicomp/Micromedex API call, not caller-supplied text
3. EHR medication reconciliation — `medication_list` should be pulled from verified EHR medication list, not free-text
4. Pharmacist order verification gate — any flagged interaction must be reviewed by a clinical pharmacist before dispensing
5. Renal/hepatic dosing calculator — dose adjustment recommendations should be backed by validated calculators (e.g. MDCalc CrCl, Cockcroft-Gault)

---

### 4. `AdverseEventTriageWorkflow` [veto]

**Decision class:** Pharmacovigilance reporting — serious unexpected ADRs trigger mandatory FDA/EMA expedited reporting with legal deadlines (7 days for fatal/life-threatening; 15 days for other serious unexpected).

**Request dataclass:** `AdverseEventRequest`
```
product_name: str           # drug/device/biologic name, lot number, manufacturer
event_description: str      # adverse event narrative (MedDRA-compatible terminology preferred)
patient_demographics: str   # age, sex, relevant comorbidities (de-identified)
event_onset: str            # timeline: product start date, event onset date, duration
causality_assessment: str   # reporter's causality: certain / probable / possible / unlikely / unrelated
concomitant_medications: str # other products at time of event
outcome: str                # recovered / recovering / not recovered / recovered with sequelae / fatal / unknown
prior_reports: str          # known signal for this product-event combination (from FAERS / EudraVigilance or sponsor safety database)
```

**Convergence gate:**
- Score ≥ 8.0
- AND zero SEVERITY FLAGS
- AND zero CAUSALITY FLAGS
- AND zero REGULATORY FLAGS
- AND no REVIEWER VETO

**Veto triggers:**
- Serious unexpected ADR (not in current product labeling per `prior_reports`) with causality ≥ possible → mandatory expedited report required; reviewer halts loop and directs pharmacovigilance officer to initiate MedWatch / EudraVigilance filing
- Fatal outcome with causality ≥ possible and event not in labeling → 7-day expedited reporting clock
- Life-threatening outcome with causality ≥ probable → 7-day expedited reporting clock

**Checklist owner:** Pharmacovigilance officer / drug safety scientist

**Score threshold:** 8.0

**PRODUCTION_GAPS:**
1. PHI de-identification — all patient fields are free-text; caller's responsibility; production requires validated de-identification before entry
2. Safety database integration — `prior_reports` should be pulled from FDA FAERS, EudraVigilance, and sponsor safety database, not caller-supplied text
3. MedWatch / EudraVigilance filing automation — AI output is advisory; actual regulatory submission is human-executed via MedWatch Online or EudraVigilance gateway
4. MedDRA coding validation — `event_description` should be coded to MedDRA PT/SOC by a qualified medical coder before submission
5. Sponsor SUSAR notification — for clinical trials, sponsor must be notified per ICH E2A; AI output does not substitute for qualified physician causality assessment

---

### 5. `PriorAuthorizationReviewWorkflow` [no veto]

**Decision class:** Payer medical necessity determination — denial has financial and access consequences; bad-faith denial has regulatory exposure (21st Century Cures Act, state PA laws).

**Request dataclass:** `PriorAuthRequest`
```
member_id: str            # de-identified member reference
requested_service: str    # CPT/HCPCS code + service description
clinical_rationale: str   # provider's medical necessity justification narrative
diagnosis_codes: str      # relevant ICD-10-CM diagnosis codes with descriptions
clinical_guidelines: str  # applicable coverage policy / clinical criteria (InterQual, MCG)
member_history: str       # relevant prior auths, diagnoses, labs, treatment history
alternatives_tried: str   # step therapy documentation (drugs/services tried and failed)
```

**Convergence gate:**
- Score ≥ 7.5
- AND zero MEDICAL-NECESSITY FLAGS
- AND zero COVERAGE FLAGS
- AND zero DOCUMENTATION FLAGS

**Checklist owner:** Prior authorization nurse / case manager

**PRODUCTION_GAPS:**
1. PHI de-identification — all fields are free-text; caller's responsibility
2. Real-time eligibility verification — coverage, benefits, and accumulator data should be pulled from payer claims system
3. InterQual / MCG integration — clinical criteria should be retrieved from licensed clinical decision support tool, not caller-supplied text
4. PA system integration — approval/denial decision must be entered into PA management system (e.g. Cohere, AIM) by authorized reviewer
5. Peer-to-peer review gate — denials must be reviewed by a physician before issuance; AI output is pre-review advisory only

---

### 6. `ClaimsAppealReviewWorkflow` [no veto]

**Decision class:** Payer denial appeal — upholding a denial against clinical evidence creates bad-faith liability; overturn must be documented against coverage policy.

**Request dataclass:** `ClaimsAppealRequest`
```
claim_id: str                    # de-identified claim reference
denied_service: str              # CPT/HCPCS code + original denial reason code
appeal_narrative: str            # member/provider appeal letter text
clinical_evidence: str           # supporting clinical documentation submitted with appeal
coverage_policy: str             # applicable payer coverage policy text
original_review_summary: str     # initial reviewer's reasoning and criteria applied
treating_physician_statement: str # attending physician supporting statement
```

**Convergence gate:**
- Score ≥ 7.5
- AND zero EVIDENCE FLAGS
- AND zero COVERAGE FLAGS
- AND zero PROCEDURE FLAGS

**Checklist owner:** Appeals coordinator / medical director

**PRODUCTION_GAPS:**
1. PHI de-identification — all fields are free-text; caller's responsibility
2. Claims system integration — claim adjudication history, EOB, and remittance data should be pulled from claims platform (e.g. TriZetto, Facets)
3. Coverage policy version control — `coverage_policy` should reference the effective-date-versioned policy from the payer's coverage library
4. Medical director sign-off gate — first-level appeals require clinical reviewer; second-level requires medical director; AI output is pre-review advisory only
5. ERISA / state appeal timeline tracking — appeal deadlines (72 hours urgent, 30 days standard) must be tracked in the payer's workflow system, not by the AI

---

### 7. `DiagnosisCodeAuditWorkflow` [no veto]

**Decision class:** ICD-10-CM/PCS and DRG accuracy — upcoding is fraud; undercoding leaves legitimate reimbursement uncaptured; both carry compliance exposure.

**Request dataclass:** `DiagnosisCodeAuditRequest`
```
encounter_summary: str    # clinical documentation excerpt (H&P, discharge summary, op note)
proposed_codes: str       # ICD-10-CM/PCS or CPT codes with descriptions proposed by coder
provider_specialty: str   # specialty context for coding conventions (e.g. cardiology, orthopedics)
payer_guidelines: str     # payer-specific coding guidelines or LCD/NCD references
previous_audits: str      # prior coding audit findings for this provider or encounter type
clinical_context: str     # admission type (IP/OP/ED), procedure details, LOS
```

**Convergence gate:**
- Score ≥ 7.5
- AND zero ACCURACY FLAGS
- AND zero COMPLIANCE FLAGS
- AND zero SPECIFICITY FLAGS

**Checklist owner:** Health information manager / certified coder (CCS/CPC)

**PRODUCTION_GAPS:**
1. PHI de-identification — all fields are free-text; caller's responsibility
2. EHR documentation integration — `encounter_summary` should be pulled from the EHR clinical documentation, not manually excerpted
3. Live coding reference — ICD-10-CM/PCS guidelines, AHA Coding Clinic, and CPT Assistant should be integrated as authoritative references, not caller-supplied text
4. Certified coder review gate — all AI-suggested code changes must be reviewed and confirmed by a credentialed coder before claim submission
5. RAC / OIG audit trail — any code changes must be documented with rationale for compliance audit purposes

---

### 8. `DischargePlanningRiskWorkflow` [no veto]

**Decision class:** Discharge readiness and post-acute care planning — premature discharge increases 30-day readmission risk; inadequate social support creates safety and SDOH gaps.

**Request dataclass:** `DischargePlanningRequest`
```
patient_summary: str            # age, diagnosis, functional status, support system (de-identified)
hospitalization_summary: str    # admission reason, treatments, procedures, length of stay
proposed_discharge_plan: str    # discharge destination, follow-up appointments, medication changes
social_determinants: str        # housing stability, transportation, food security, insurance status
readmission_history: str        # prior 30-day readmissions and contributing factors
care_team_notes: str            # nursing, PT/OT, social work, case management notes
```

**Convergence gate:**
- Score ≥ 7.5
- AND zero READMISSION FLAGS
- AND zero CARE-GAP FLAGS
- AND zero SOCIAL-DETERMINANT FLAGS

**Checklist owner:** Discharge planner / social worker / care coordinator

**PRODUCTION_GAPS:**
1. PHI de-identification — all fields are free-text; caller's responsibility
2. EHR integration — patient summary, hospitalization history, and care team notes should be pulled from EHR (Epic, Cerner) at discharge planning time
3. Real-time bed availability — post-acute care placement depends on real-time SNF/IRF/LTACH bed availability not captured in free-text
4. Payer authorization — post-acute services require prior authorization from the payer; AI output does not constitute authorization
5. Readmission risk model — production should use a validated readmission risk model (LACE, HOSPITAL score) as the baseline; LLM provides contextual adjustment, not the baseline score

---

## Phase-2 catalog (19 locked designs, not built)

| # | Workflow | Veto? | Sub-domain | Likely-first |
|---|---|---|---|---|
| 9 | `PHIBreachScopeWorkflow` | ✅ | Compliance | ✅ |
| 10 | `MentalHealthCrisisRiskWorkflow` | ✅ | Clinical | ✅ |
| 11 | `SurgerySiteRiskAssessmentWorkflow` | ✅ | Clinical | — |
| 12 | `RadiologyReportReviewWorkflow` | ✅ | Clinical | — |
| 13 | `SubstanceUseTreatmentEligibilityWorkflow` | — | Clinical | ✅ |
| 14 | `ClinicalDocumentationImprovementWorkflow` | — | Payer/Admin | ✅ |
| 15 | `FormularyExceptionRequestWorkflow` | — | Payer/Admin | — |
| 16 | `UtilizationManagementReviewWorkflow` | — | Payer/Admin | — |
| 17 | `NetworkAdequacyAssessmentWorkflow` | — | Payer/Admin | — |
| 18 | `MedicalNecessitySecondReviewWorkflow` | — | Payer/Admin | — |
| 19 | `HealthTechnologyAssessmentWorkflow` | — | Payer/Admin | — |
| 20 | `ClinicalTrialProtocolReviewWorkflow` | — | Pharma | — |
| 21 | `PostMarketSurveillanceWorkflow` | — | Pharma | — |
| 22 | `GeneticTestingOrderReviewWorkflow` | — | Clinical | — |
| 23 | `InfectionControlRiskAssessmentWorkflow` | — | Clinical | — |
| 24 | `PopulationHealthStratificationWorkflow` | — | Population | — |
| 25 | `CarePlanAdherenceReviewWorkflow` | — | Clinical | — |
| 26 | `ValueBasedCareMetricsWorkflow` | — | Admin | — |
| 27 | `SocialDeterminantsInterventionWorkflow` | — | Population | — |

**27 workflows total: 8 MVP + 19 Phase-2. 8 veto-using across full catalog (4 MVP + 4 Phase-2).**

Likely-first Phase-2 promotions: PHIBreachScope [veto], MentalHealthCrisisRisk [veto], SubstanceUseTreatmentEligibility, ClinicalDocumentationImprovement.

---

## Universal PRODUCTION_GAPS (all 8 workflows)

1. **PHI de-identification** — all patient-identifying fields are caller-supplied free-text; the workflow applies `sanitize_for_prompt` but cannot validate de-identification; production requires a HIPAA-compliant de-identification pipeline upstream of every request
2. **EHR/EMR integration** — Epic, Cerner, Meditech, or equivalent; all clinical fields should be pulled from authoritative source systems, not manually entered
3. **Live clinical reference databases** — Lexicomp/Micromedex (drug interactions), InterQual/MCG (prior auth), ICD-10-CM Tabular (coding), formulary management systems
4. **Human clinical sign-off gate** — no workflow output may trigger an automated clinical action; a qualified clinician or reviewer retains full decision authority
5. **Regulatory filing automation** — ADR triage output is advisory; MedWatch/EudraVigilance submission, prior auth letters, and denial notices are human-executed
6. **Append-only audit store** — session-local JSON ledger only; production requires a tamper-evident audit store for regulatory review (FDA, CMS, OIG)
7. **Dedicated third-model clinical auditor** — single-stage reviewer folds quality + domain audit; production should run a separately configured auditor model for each high-stakes flag class (bias, contraindication, causality)

---

## Build sequence (MVP-8)

Recommended ship order — complexity increases, shared patterns solidify early:

1. **`DiagnosisCodeAuditWorkflow`** — simplest (no veto, clear flag classes, no life-safety stakes); establishes pattern
2. **`DischargePlanningRiskWorkflow`** — no veto, SDOH flag class is novel; validates SOCIAL-DETERMINANT FLAGS parser
3. **`PriorAuthorizationReviewWorkflow`** — no veto, payer persona; validates MEDICAL-NECESSITY FLAGS parser
4. **`ClaimsAppealReviewWorkflow`** — no veto, mirrors prior auth structure; fast follow
5. **`DrugInteractionFlaggingWorkflow`** [veto] — first veto workflow; validates veto criteria at 8.0 threshold
6. **`AdverseEventTriageWorkflow`** [veto] — veto with regulatory citation language; validates D-HEALTH-4
7. **`TreatmentPlanReviewWorkflow`** [veto] — most complex clinical reasoning; depends on drug interaction patterns
8. **`ClinicalTrialEligibilityWorkflow`** [veto] — bias-gate + veto combined; most complex; anchors Phase-2 bias patterns

Security audit on the full healthcare surface before commit (per domain-add convention; audit cadence: every new domain before commit).
