---
marp: true
theme: adv-slides
paginate: true
---

<!-- _class: lead -->

# Healthcare Domain
## Adversarial Multi-Agent Collaboration for Clinical, Payer, and Drug-Safety Decisions

Diagnosis Coding · Discharge Planning · Prior Auth · Claims Appeals · Drug Interaction · Adverse Event · Treatment Plan · Trial Eligibility

&nbsp;

*Domain application of the adv-multi-agent library*
*Clinical Decision Support + Payer Operations + Drug Safety · May 2026*

&nbsp;

*Based on ARIS (Yang, Li, Li — SJTU + Shanghai Innovation Institute, arXiv:2605.03042)*

---

<!-- _class: section -->

# Problem Statement
*Why adversarial multi-agent for healthcare?*

Healthcare decisions concentrate the four properties ARIS targets:

| Property | Healthcare manifestation |
|---|---|
| **Irreversibility** | Trial enrollment, contraindicated treatment, adverse event report — patient-safety or regulatory consequence that cannot be undone |
| **Regulator audit-trail** | FDA 21 CFR Part 11/312 (ADR reporting) · CMS 21st Century Cures Act (prior auth timelines) · HIPAA · IRB/ICH-GCP (trial eligibility) |
| **Asymmetric information** | Clinician knows comorbidities the coder doesn't · pharmacist knows interaction database the prescriber paraphrased · payer reviewer knows policy version the appeals coordinator is arguing against |
| **Echo-chamber risk** | Clinicians + payer reviewers develop precedent bias · same-family LLMs replicate it · load-bearing on demographic bias in trial enrollment + bad-faith PA denial |

> Cross-family reviewer is the safeguard.

---

# Why Scale Demands the Pattern

Healthcare decisions are high-volume and high-stakes simultaneously:

| Decision | Volume | Per-instance stake |
|---|---|---|
| Diagnosis coding audit | Per encounter (millions/year) | Upcoding = fraud; undercoding = lost revenue + compliance exposure |
| Discharge planning | Per inpatient stay | Premature discharge → 30-day readmission penalty; SDOH gaps → safety event |
| Prior authorization | Per service request | Bad-faith denial → 21st Century Cures Act regulatory exposure |
| Claims appeal | Per denial | Evidence-blind uphold → ERISA / state bad-faith liability |
| Drug interaction | Per new prescription | Absolute contraindication missed → patient harm; QTc combination → cardiac event |
| Adverse event triage | Per ADR report | Mandatory 7/15-day reporting missed → FDA enforcement + safety signal lost |
| Treatment plan review | Per prescribing decision | Contraindicated treatment → irreversible patient harm |
| Trial eligibility | Per enrollment | Demographic bias → JAMA 2019 documented inequity; wrong exclusion → patient denied access |

A confident-but-wrong LLM across this surface produces upcoding exposure, bad-faith denials, missed ADR reports, contraindicated prescriptions, and biased trial enrollment — each independently harmful.

> Human clinical sign-off is required on every recommendation — but auditing the *recommendation engine* improves the human's leverage.

---

# ARIS Pattern Recap

Two models from different families propose and challenge the same recommendation. Failures correlated within a model family are caught by the other:

```
healthcare.*Request   (8 MVP variants; 27 in the full catalog)
  │
  ▼
Executor (Claude Opus 4.7, adaptive thinking)
  │  produces evidence-grounded advisory brief
  ▼
Reviewer (GPT-4o — different family, multi-mandate)
  │  1. Quality audit                   (score 0–10)
  │  2. Domain audit                    (3 flag classes per workflow)
  │  3. Reviewer veto                   (4 workflows — patient-safety + regulatory irreversibles)
  ▼
score ≥ threshold AND zero domain flags AND no veto?
  YES → converged, return output
  NO  → executor revises (critique + flags injected)
         repeat until convergence or MAX_REVIEW_ROUNDS
```

**Convergence is a conjunction** — quality gate *and* every domain-flag class clear *and* (for veto-using workflows) no veto.

**Score threshold:** 7.5 for non-veto workflows · **8.0 for veto-using workflows** (D-HEALTH-2 — patient-safety and regulatory stakes justify elevated bar).

---

# Why Healthcare Fits the ARIS Pattern

Four structural properties make cross-family adversarial review particularly valuable:

**1. PHI boundary (D-HEALTH-3)** — All patient-identifying fields are caller-supplied free-text. `sanitize_for_prompt` strips control chars and bounds length. It cannot validate de-identification. PHI handling is the caller's responsibility at every stage.

**2. Regulatory citation precision (D-HEALTH-4)** — Veto trigger language cites specific regulatory references (FDA 21 CFR 312 7/15-day expedited reporting, ICH E2A, JAMA 2019 Duma et al. demographic-bias literature). Generic "safety concern" phrasing is not acceptable — it cannot be acted on by a pharmacovigilance officer or IRB coordinator.

**3. Bias-gate pattern lineage** — `ClinicalTrialEligibilityWorkflow` applies the bias-gate pattern from `parole.RecidivismRiskWorkflow` to clinical research. Cross-model reviewer is the structural safeguard against demographic exclusion that the same-family LLM would replicate from training-data precedent.

**4. No domain base class (D-HEALTH-1 / D-IND-1 / D-RETAIL-7)** — Per-flag-header banners, checklist text, and veto criteria diverge enough across workflows that a base class costs more than it saves. Helper-level sharing (`core/_internal.py`) is the right unit of reuse.

---

# MVP-8 Catalog
*D-HEALTH-1 — MVP-8 of 27-workflow catalog; 19 Phase-2 designs locked*

| Sub-domain | MVP | Phase 2 (selected) |
|---|---|---|
| **Clinical** (2 MVP + 5 Phase-2) | `TreatmentPlanReview` ✅ (veto) · `ClinicalTrialEligibility` ✅ (veto) | `MentalHealthCrisisRisk` (veto) · `SurgerySiteRisk` (veto) · `RadiologyReportReview` (veto) · `SubstanceUseTreatmentEligibility` · `GeneticTestingOrderReview` |
| **Drug Safety** (2 MVP + 2 Phase-2) | `DrugInteractionFlagging` ✅ (veto) · `AdverseEventTriage` ✅ (veto) | `PostMarketSurveillance` · `ClinicalTrialProtocolReview` |
| **Payer / Admin** (4 MVP + 8 Phase-2) | `DiagnosisCodeAudit` ✅ · `DischargePlanningRisk` ✅ · `PriorAuthorizationReview` ✅ · `ClaimsAppealReview` ✅ | `ClinicalDocumentationImprovement` · `FormularyExceptionRequest` · `UtilizationManagementReview` · `PHIBreachScope` (veto) · `MedicalNecessitySecondReview` + 3 more |
| **Population** (0 MVP + 4 Phase-2) | — | `PopulationHealthStratification` · `CarePlanAdherenceReview` · `ValueBasedCareMetrics` · `SocialDeterminantsIntervention` |

8 of 8 MVP triple-flag · 4 of 8 MVP add reviewer veto. Elevated veto count vs industrial (4/8 vs 2/8) reflects patient-safety and mandatory-reporting stakes.

---

# MVP-8 Selection Rationale

| # | Workflow | Veto? | Why MVP |
|---|---|---|---|
| 1 | `DiagnosisCodeAuditWorkflow` | — | Highest-volume coding decision; simplest flag pattern; establishes domain baseline |
| 2 | `DischargePlanningRiskWorkflow` | — | SDOH flag class is novel; validates SOCIAL-DETERMINANT FLAGS parser |
| 3 | `PriorAuthorizationReviewWorkflow` | — | Payer persona; 21st Century Cures Act regulatory pressure makes this a priority |
| 4 | `ClaimsAppealReviewWorkflow` | — | Mirrors prior auth structure; validates EVIDENCE + COVERAGE + PROCEDURE flag pattern |
| 5 | `DrugInteractionFlaggingWorkflow` | ✅ | First veto workflow; QTc + NTI + cross-allergy veto criteria are unambiguous halt rationale |
| 6 | `AdverseEventTriageWorkflow` | ✅ | 7/15-day expedited reporting mandate; regulatory citation language validates D-HEALTH-4 |
| 7 | `TreatmentPlanReviewWorkflow` | ✅ | Most complex clinical reasoning; contraindication veto anchors patient-safety case |
| 8 | `ClinicalTrialEligibilityWorkflow` | ✅ | Bias-gate + veto combined; parole-lineage pattern applied to clinical research; JAMA 2019 anchor |

Cross-domain reuse: `pc.CyberUnderwritingWorkflow` for healthcare provider cyber risk; `industrial.AdverseEventTriage` shape informs pharmacovigilance cascade design; parole bias-gate → trial eligibility bias-gate (direct lineage).

---

# Per-Workflow Detail: Non-Veto Track (1/2)

---

## `DiagnosisCodeAuditWorkflow`

**Triple-flag, no veto.** ICD-10-CM/PCS and DRG accuracy — upcoding is fraud; undercoding is uncaptured revenue + compliance exposure.

**Request fields:** `encounter_summary`, `proposed_codes`, `provider_specialty`, `payer_guidelines`, `previous_audits`, `clinical_context`.

**Flag classes:**
- `ACCURACY FLAGS` — code-to-documentation concordance; principal diagnosis sequencing; CC/MCC capture; DRG grouper impact
- `COMPLIANCE FLAGS` — upcoding signal; LCD/NCD applicability; coding convention violations (ICD-10-CM Official Guidelines); RAC/OIG audit exposure
- `SPECIFICITY FLAGS` — unspecified-code usage when specificity is documented; laterality; encounter type; procedure coding granularity

No veto — coding decisions are reversible via corrected claim submission before the timely-filing limit.

**Checklist owner:** Health information manager / certified coder (CCS/CPC)
**Score threshold:** 7.5
**Skill templates (4):** `diagnosis_initial`, `diagnosis_revision`, `diagnosis_review`, `diagnosis_checklist`.

---

## `DischargePlanningRiskWorkflow`

**Triple-flag, no veto.** Discharge readiness and post-acute placement — premature discharge increases 30-day readmission risk; inadequate SDOH support creates safety gaps.

**Request fields:** `patient_summary`, `hospitalization_summary`, `proposed_discharge_plan`, `social_determinants`, `readmission_history`, `care_team_notes`.

**Flag classes:**
- `READMISSION FLAGS` — clinical instability indicators; medication reconciliation gaps; inadequate follow-up appointment timing; condition-specific readmission risk factors (HF, COPD, PNA, CABG)
- `CARE-GAP FLAGS` — missing post-acute orders; physical/occupational therapy gaps; home health eligibility not addressed; DME orders incomplete
- `SOCIAL-DETERMINANT FLAGS` — housing instability; transportation barrier to follow-up; food insecurity; informal support system gaps; insurance coverage for post-acute services

No veto — discharge timing is a clinical judgment call reserved for attending physician + care team.

**Checklist owner:** Discharge planner / social worker / care coordinator
**Score threshold:** 7.5
**Skill templates (4):** `discharge_initial`, `discharge_revision`, `discharge_review`, `discharge_checklist`.

---

# Per-Workflow Detail: Non-Veto Track (2/2)

---

## `PriorAuthorizationReviewWorkflow`

**Triple-flag, no veto.** Payer medical necessity determination — denial has financial and access consequences; bad-faith denial has regulatory exposure (21st Century Cures Act, state PA laws).

**Request fields:** `member_id`, `requested_service`, `clinical_rationale`, `diagnosis_codes`, `clinical_guidelines`, `member_history`, `alternatives_tried`.

**Flag classes:**
- `MEDICAL-NECESSITY FLAGS` — clinical rationale does not meet guideline criteria cited; step therapy not documented; alternative services not addressed; clinical evidence mischaracterized
- `COVERAGE FLAGS` — service not covered under cited benefit; effective date mismatch; benefit limit reached but not documented; coverage policy version mismatch
- `DOCUMENTATION FLAGS` — treating physician statement absent; lab / imaging / clinical notes not attached; denial notice missing required regulatory content; peer-to-peer review not offered

No veto — PA determination is reversible via peer-to-peer review + appeal.

**Checklist owner:** Prior authorization nurse / case manager
**Score threshold:** 7.5
**Skill templates (4):** `prior_auth_initial`, `prior_auth_revision`, `prior_auth_review`, `prior_auth_checklist`.

---

## `ClaimsAppealReviewWorkflow`

**Triple-flag, no veto.** Payer denial appeal — upholding a denial against clinical evidence creates bad-faith liability; overturn must be documented against coverage policy.

**Request fields:** `claim_id`, `denied_service`, `appeal_narrative`, `clinical_evidence`, `coverage_policy`, `original_review_summary`, `treating_physician_statement`.

**Flag classes:**
- `EVIDENCE FLAGS` — clinical evidence submitted contradicts denial rationale; treating physician statement not addressed; literature citation not evaluated; evidence strength mischaracterized
- `COVERAGE FLAGS` — coverage policy cited does not match effective date; policy interpretation conflicts with plan documents; member's benefit differs from cited policy
- `PROCEDURE FLAGS` — CPT/HCPCS code mismatch between claim and appeal; modifier applicability not addressed; bundling/unbundling analysis absent

No veto — appeals are reversible and are themselves the escalation channel.

**Checklist owner:** Appeals coordinator / medical director
**Score threshold:** 7.5
**Skill templates (4):** `claims_appeal_initial`, `claims_appeal_revision`, `claims_appeal_review`, `claims_appeal_checklist`.

---

# Per-Workflow Detail: Veto Track (1/4)

---

## `DrugInteractionFlaggingWorkflow`

**Veto + triple-flag.** Polypharmacy safety — absolute contraindications and life-threatening interactions are patient-safety irreversibles.

**Request fields:** `patient_id`, `medication_list`, `new_medication`, `indication`, `renal_function`, `hepatic_function`, `allergy_history`, `formulary_reference`.

**Flag classes:**
- `SEVERITY FLAGS` — interaction severity tier (major / moderate / minor) per standard reference; pharmacodynamic vs pharmacokinetic mechanism; onset time (rapid / delayed); documentation level (established / probable / suspected / theoretical)
- `EVIDENCE FLAGS` — clinical evidence basis; whether `formulary_reference` contains complete contraindication data or is paraphrased; missing renal/hepatic dosing adjustment analysis
- `CONTRAINDICATION FLAGS` — absolute contraindication presence; QTc-prolonging combination; narrow-therapeutic-index interaction without dose adjustment; cross-allergy with `allergy_history`

**Veto criteria:** absolute contraindication between `new_medication` and any drug in `medication_list` · QTc-prolonging combination in patient with documented cardiac history or prolonged baseline QTc · narrow-therapeutic-index interaction (warfarin + NSAID, lithium + thiazide) with no dose adjustment plan · cross-allergy with documented allergy in `allergy_history`.

**Checklist owner:** Clinical pharmacist
**Score threshold:** 8.0 (D-HEALTH-2)
**Skill templates (4):** `drug_initial`, `drug_revision`, `drug_review`, `drug_checklist`.

---

## `AdverseEventTriageWorkflow`

**Veto + triple-flag.** Pharmacovigilance reporting — serious unexpected ADRs trigger mandatory FDA/EMA expedited reporting with legal deadlines (7 days for fatal/life-threatening; 15 days for other serious unexpected).

**Request fields:** `product_name`, `event_description`, `patient_demographics`, `event_onset`, `causality_assessment`, `concomitant_medications`, `outcome`, `prior_reports`.

**Flag classes:**
- `SEVERITY FLAGS` — CTCAE grade; seriousness criteria (death / life-threatening / hospitalization / disability / congenital anomaly / important medical event); relatedness to study/marketed product
- `CAUSALITY FLAGS` — causality grading (certain / probable / possible / unlikely / unrelated); temporal relationship quality; dechallenge / rechallenge evidence; alternative explanations; `prior_reports` database concordance
- `REGULATORY FLAGS` — expedited reporting trigger met (7-day or 15-day per FDA 21 CFR 312 / ICH E2A); MedWatch Form 3500A / EudraVigilance ICSR completeness; SUSAR notification obligation (clinical trial context); MedDRA coding adequacy

**Veto criteria (D-HEALTH-4):** serious unexpected ADR (not in current labeling per `prior_reports`) with causality ≥ possible → mandatory expedited report; reviewer halts and directs pharmacovigilance officer to initiate MedWatch / EudraVigilance filing · fatal outcome with causality ≥ possible and event not in labeling → 7-day FDA 21 CFR 312 expedited reporting clock · life-threatening outcome with causality ≥ probable → 7-day expedited reporting clock · sponsor SUSAR notification obligation under ICH E2A not addressed.

**Checklist owner:** Pharmacovigilance officer / drug safety scientist
**Score threshold:** 8.0 (D-HEALTH-2)
**Skill templates (4):** `adverse_initial`, `adverse_revision`, `adverse_review`, `adverse_checklist`.

---

# Per-Workflow Detail: Veto Track (2/4)

---

## `TreatmentPlanReviewWorkflow`

**Veto + triple-flag.** Clinical prescribing — contraindicated treatment can cause irreversible patient harm.

**Request fields:** `patient_summary`, `proposed_plan`, `current_medications`, `lab_values`, `clinical_guidelines`, `contraindication_context`.

**Flag classes:**
- `GUIDELINE FLAGS` — evidence base for proposed medication/procedure (GRADE A/B/C/D); discordance with applicable clinical practice guidelines; off-label use without supporting evidence; dose/route/duration outside guideline range
- `CONTRAINDICATION FLAGS` — absolute and relative contraindications given comorbidities; drug-organ-failure interaction (renal/hepatic dosing not adjusted per eGFR/Child-Pugh); drug-disease contraindication; pregnancy/lactation safety not addressed when relevant
- `RISK FLAGS` — benefit-risk balance assessment; monitoring requirements not specified; patient-specific risk factors not addressed (age extremes, polypharmacy, frailty score); baseline labs required before initiation absent

**Veto criteria:** absolute drug-allergy contraindication present in `patient_summary` or `contraindication_context` · drug-organ-failure contraindication (renally-cleared drug at full dose with eGFR below threshold per guidelines) · procedure listed in `proposed_plan` is contraindicated given documented comorbidity or medication · treatment initiated without required baseline monitoring ordered.

**Checklist owner:** Attending physician
**Score threshold:** 8.0 (D-HEALTH-2)
**Skill templates (4):** `treatment_initial`, `treatment_revision`, `treatment_review`, `treatment_checklist`.

---

## `ClinicalTrialEligibilityWorkflow`

**Veto + triple-flag.** IRB-governed patient enrollment — irreversible once enrolled or excluded; demographic bias is documented in trial enrollment literature (JAMA 2019 Duma et al.).

**Request fields:** `trial_id`, `protocol_summary`, `patient_profile`, `biomarker_status`, `prior_treatments`, `competing_risks`, `site_context`.

**Flag classes:**
- `BIAS FLAGS` — protected-class attribute (race, sex, age, disability) used as determinative exclusion factor without protocol-specified clinical justification; age range broader than necessary for primary endpoint; site-level demographic constraint not in protocol; JAMA 2019 Duma et al. demographic-exclusion pattern
- `ELIGIBILITY FLAGS` — inclusion/exclusion criteria applied incorrectly against `protocol_summary`; biomarker status misinterpreted; prior treatment exclusion window misapplied; competing-risk condition status misclassified
- `EVIDENCE FLAGS` — eligibility determination contradicts primary evidence in `protocol_summary` or `biomarker_status`; relevant comorbidity in `patient_profile` not evaluated against exclusion criteria; site-level protocol deviation not surfaced

**Veto criteria (D-HEALTH-4):** patient meets a life-threatening exclusion criterion (organ dysfunction, prohibited concomitant med, active infection per protocol) but draft marks eligible · protected-class attribute (race, sex, age, disability) appears to be a determinative exclusion factor without protocol-specified clinical justification · eligibility determination contradicts primary evidence in `protocol_summary` or `biomarker_status`.

**Bias-gate lineage:** parole `RecidivismRiskWorkflow` → clinical trial eligibility. Cross-model reviewer is the structural safeguard against same-family-LLM replication of training-data demographic exclusion precedent.

**Checklist owner:** IRB coordinator / principal investigator
**Score threshold:** 8.0 (D-HEALTH-2)
**Skill templates (4):** `trial_initial`, `trial_revision`, `trial_review`, `trial_checklist`.

---

# Veto Pattern

*4 veto workflows · patient-safety + regulatory irreversibles · D-HEALTH-2 / D-HEALTH-4*

All 4 veto workflows use the same dict-iteration pattern as industrial, with veto interleaved:

```python
_FLAG_HEADERS: tuple[str, ...] = (
    "SEVERITY FLAGS:",
    "EVIDENCE FLAGS:",
    "CONTRAINDICATION FLAGS:",
)
current: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
accumulated: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
for round_num in range(1, max_rounds + 1):
    ...
    for header in _FLAG_HEADERS:
        current[header] = extract_flags(critique, header)        # REASSIGN per round
        accumulated[header].extend(current[header])              # audit-trail accrues
    self.wiki.add_feedback(...)                                  # audit before veto break
    veto_reason = self._extract_veto(review.critique, max_wiki_chars)
    if veto_reason is not None:
        break        # halt before convergence check
    if review.approved and not any(current.values()):
        converged = True
        break
```

**Audit-trail before veto break** — vetoed round writes reviewer critique to wiki + claims to ledger before breaking. Required for FDA 21 CFR Part 11 / IRB / pharmacovigilance audit defensibility.

| Workflow | Veto trigger examples |
|---|---|
| `DrugInteractionFlaggingWorkflow` | Absolute contraindication · QTc-prolonging combination with cardiac history · NTI interaction (warfarin+NSAID, lithium+thiazide) without dose adjustment · cross-allergy |
| `AdverseEventTriageWorkflow` | Serious unexpected ADR with causality ≥ possible → 7/15-day expedited reporting clock (FDA 21 CFR 312 / ICH E2A) · fatal + not-in-labeling → 7-day clock |
| `TreatmentPlanReviewWorkflow` | Absolute drug-allergy contraindication · drug-organ-failure without dose adjustment (eGFR) · procedure contraindicated by documented comorbidity |
| `ClinicalTrialEligibilityWorkflow` | Life-threatening exclusion criterion met but draft marks eligible · protected-class determinative exclusion without protocol justification · contradicts primary protocol evidence |

> Veto rate (4/8 = 50%) is the highest across all domains — reflects the proportion of healthcare decisions with patient-safety or mandatory-reporting irreversibility.

---

# Bias-Gate Pattern

*`ClinicalTrialEligibilityWorkflow` — parole lineage applied to clinical research*

**The documented problem:** JAMA 2019 (Duma et al.) — clinical trial enrollment systematically underrepresents women, elderly patients, racial minorities, and patients with comorbidities. Same-family LLMs trained on trial protocol literature replicate these exclusion patterns. Cross-model reviewer is the structural intervention.

**How the BIAS FLAGS gate works:**

```
Executor draft: "Patient profile excludes age > 75 — consistent with protocol"
                ↓
Reviewer checks: Is this exclusion criterion in protocol_summary?
                 Does it have a clinical justification (pharmacokinetics, safety endpoint)?
                 OR is it a surrogate demographic proxy?
                ↓
If demographic proxy without clinical justification:
    BIAS FLAGS: ["Age exclusion > 75 not in protocol inclusion criteria; no pharmacokinetic
                  rationale provided; JAMA 2019 Duma et al. pattern — flag for PI review"]
    → executor must address before convergence
```

**Veto vs flag distinction:**
- **FLAG** → re-inject into next executor round; executor must address and justify or revise
- **VETO** → halt loop immediately; draft is preserved in `metadata['first_draft']`; PI + IRB coordinator must review before any enrollment action

**Protected attributes guarded:** race, sex (including pregnancy status), age beyond age-range inclusion criteria, disability status, socioeconomic proxy variables (insurance type, zip code as surrogate for race/income).

**Clinical justification carve-out (D-HEALTH-4):** Pediatric age criteria with explicit protocol pharmacokinetic justification are not flagged. The reviewer template reads: "age (beyond age-range inclusion criteria *with clinical justification*)" — the italicized qualifier prevents false-positive bias flags on legitimately age-stratified trials.

---

# Production Gaps

*Universal across all 8 healthcare workflows — required before any pilot deployment*

| # | Gap | Why it matters |
|---|---|---|
| 1 | **PHI de-identification** — caller's responsibility; HIPAA Safe Harbor / Expert Determination | `sanitize_for_prompt` strips control chars; it cannot validate de-identification. Every workflow PRODUCTION_GAPS #1. D-HEALTH-3. |
| 2 | **EHR/EMR integration** — Epic / Cerner / Meditech for clinical fields | Free-text inputs are paraphrased; production requires structured pull from authoritative source systems |
| 3 | **Live clinical reference databases** — Lexicomp / Micromedex (drug interactions), InterQual / MCG (prior auth), ICD-10-CM Tabular (coding) | Caller-supplied text is not a live formulary; contraindication coverage is incomplete |
| 4 | **Human clinical sign-off gate** — no workflow output may trigger automated clinical action | AI output is advisory; attending physician / pharmacist / IRB retains full decision authority |
| 5 | **Regulatory filing automation** — MedWatch / EudraVigilance / prior auth letters are human-executed | Veto directs the pharmacovigilance officer to file; the AI does not submit the ICSR |
| 6 | **Append-only audit store** — session-local JSON only; production needs tamper-evident store for FDA / CMS / OIG | 21 CFR Part 11 compliance requires audit trail integrity guarantees beyond file-write |
| 7 | **Dedicated third-model clinical auditor** — single-stage reviewer folds quality + domain audit | Production should run a separately configured auditor per high-stakes flag class (bias, contraindication, causality) per ARIS §3.1 |

> Per-workflow PRODUCTION_GAPS docstrings also list: pharmacovigilance database integration, IRB/EDC sign-off gate, renal/hepatic dosing calculator, ERISA/state appeal timeline tracking, validated readmission risk model (LACE/HOSPITAL score).

---

# Audit Posture

*6 audit cycles · 0 open findings across all 36 workflows (research + parole + retail + pc + industrial + healthcare)*

| Cycle | Date | Domain | CRIT | HIGH | MED | LOW | Status |
|---|---|---|---|---|---|---|---|
| 1 | 2026-05-12 | research | 0 | 0 | 1 | 3 | ✅ All closed |
| 2 | 2026-05-13 | parole + retail | 0 | 0 | 1 | 5 | ✅ All closed |
| 3 | 2026-05-14 AM | pc | 0 | 0 | 1 | 5 | ✅ All closed |
| 4 | 2026-05-14 PM | industrial | 0 | **1** (H-IND-1) | 0 | 5 | ✅ H-IND-1 closed same-session |
| 5 | 2026-05-15–16 | retail/pc parity | 0 | 0 | 0 | 2 | ✅ All closed |
| 6 | 2026-05-16 | **healthcare** | 0 | 0 | **1** (M-HEALTH-1) | 4 | ✅ All closed same-day |

**Healthcare sweep (2026-05-16) findings:**

| Code | Severity | Finding | Status |
|---|---|---|---|
| M-HEALTH-1 | MEDIUM | Per-field-cap test uses `+5` slack in 3 of 8 test files | ✅ Closed same-day |
| L-HEALTH-1 | LOW | `metadata['first_draft']` carries PHI without caller-facing warning at assignment site | ✅ Closed |
| L-HEALTH-2 | LOW | Raw `request.field[:200]` metadata slices not passed through `sanitize_for_prompt` | ✅ Closed |
| L-HEALTH-3 | LOW | Score-threshold boundary not tested independently of flag presence in non-veto workflows | ✅ Closed |
| L-HEALTH-4 | LOW | Operator PRODUCTION_GAPS not consolidated in durable checklist file in repo | ✅ Closed |

**Prior-cycle remediations confirmed inherited uniformly:**
- M-PC-1 — `extract_veto_directive` line-anchored (veto marker opening anchor)
- H-IND-1 — `_is_sibling_header_lhs` hyphen-aware regex (`CARE-GAP FLAGS:`, `SOCIAL-DETERMINANT FLAGS:`, `MEDICAL-NECESSITY FLAGS:` all covered)
- L-PC-2/3/5 — FORMAT NOTE in veto templates · `_MAX_FIELD_CHARS=1500` · `truncate_flag_display`
- L-IND-2 — `metadata['first_draft']` on veto · L-IND-4 — `_KNOWN_DOMAINS` allowlist includes `"healthcare"`

---

# What's NOT in This Domain

*Phase-2 locked but not built · integration gaps · PyPI gap*

**19 Phase-2 workflow designs are locked** (in `2026-05-16-healthcare-domain-design.md`) but not implemented. Likely-first promotions:

| Priority | Workflow | Reason |
|---|---|---|
| 1 | `PHIBreachScopeWorkflow` (veto) | HIPAA breach notification clock (60-day) makes expedited review high-value |
| 2 | `MentalHealthCrisisRiskWorkflow` (veto) | Safety-critical; Crisis Standards of Care regulatory context |
| 3 | `SubstanceUseTreatmentEligibilityWorkflow` | 42 CFR Part 2 confidentiality adds complexity; anchors behavioral health sub-domain |
| 4 | `ClinicalDocumentationImprovementWorkflow` | CDI bridges coding + clinical; highest volume in payer-ops sub-domain |

**Integration gaps (not code gaps):**
- No EHR/EMR connector — Epic / Cerner / Meditech APIs not wired; all inputs are free-text
- No live formulary — Lexicomp / Micromedex API not integrated; `formulary_reference` is caller-supplied
- No pharmacovigilance DB — FDA FAERS / EudraVigilance / sponsor safety DB not integrated; `prior_reports` is caller-supplied
- No PA/UM system — Cohere / AIM / TriZetto / Facets not integrated; claim/auth history is caller-supplied
- No PyPI package — library is not yet pip-installable; must be cloned and installed from source

**Teaching posture is intentional** — the workflow is a reasoning scaffold demonstrating the ARIS adversarial pattern in a clinical context. It is not a clinical decision support system and must not be deployed as one.

---

# Architecture Properties

*Multi-gate convergence · reviewer-veto · claim ledger · programmatic disclaimer · same infrastructure different domain*

**Shared helpers in `core/_internal.py`** — single change propagates to every domain:

| Helper | Purpose | Healthcare usage |
|---|---|---|
| `sanitize_for_prompt` | Strip control chars + NFC + cap length | Every workflow, every text injection (request, output, critique, flags, wiki write) |
| `extract_flags` | Parse `*FLAGS:` section (M-PC-1 line-anchored + H-IND-1 hyphen-stop) | All 8 workflows; covers hyphenated headers `CARE-GAP FLAGS:`, `SOCIAL-DETERMINANT FLAGS:` |
| `extract_veto_directive` | Parse `REVIEWER VETO:` directive (M-PC-1 + H-IND-1) | 4 veto workflows: DrugInteraction, AdverseEvent, TreatmentPlan, ClinicalTrialEligibility |
| `truncate_flag_display` | Cap re-injection at 16 entries with marker | All 8 `_format_flag_section` implementations |
| `_register_claims` | Line-anchored `## Claims` split; 200-claim cap; dedup | All 8 workflows via `BaseWorkflow` |

**No domain base class** (D-HEALTH-1 / D-IND-1 / D-RETAIL-7). Per-flag-header banners, checklist ownership lines, and veto escalation text diverge enough across 8 workflows that base-class extraction costs more than it saves. Helper-level sharing is the correct unit.

**Programmatic disclaimer** — `_DISCLAIMER` is a module-level string constant in each workflow file. Appended in code as `f"{output}\n\n---\n\n{_DISCLAIMER}"` (non-veto) or via `_compose_output(output, veto_reason)` (veto). No model output or caller input can suppress or replace it. Each workflow's disclaimer names the correct approver role (certified coder, attending physician, pharmacovigilance officer, IRB coordinator, etc.).

---

# Status

*8 of 8 MVP shipped · 558 tests · 6 audit cycles closed*

| Component | Status |
|---|---|
| 8 MVP workflows (4 non-veto + 4 veto) | ✅ |
| 32 healthcare skill templates (4 per workflow) | ✅ |
| 9 healthcare examples (`examples/healthcare/*.py` + `__init__.py`) | ✅ |
| Triple-flag pattern (8 of 8 MVP) | ✅ |
| Reviewer-veto pattern (4 of 8 MVP) | ✅ |
| ~69 healthcare unit tests across 8 files | ✅ all passing |
| **558 total tests** (research + parole + retail + pc + industrial + healthcare + shared) | ✅ all passing |
| ruff + mypy clean | ✅ |
| D-HEALTH-1..4 decision rows in `decisions.md` | ✅ |
| Design doc (`docs/superpowers/specs/2026-05-16-healthcare-domain-design.md`) | ✅ — full 27-workflow catalog with MVP-8 marked |
| Focused security sweep | ✅ — M-HEALTH-1 + L-HEALTH-1..4 all closed same-day |
| 19 Phase-2 workflow designs locked | ✅ |

| Integration | Status |
|---|---|
| EHR/EMR (Epic / Cerner / Meditech) | ❌ |
| Live drug interaction DB (Lexicomp / Micromedex) | ❌ |
| Clinical criteria (InterQual / MCG) | ❌ |
| Pharmacovigilance DB (FDA FAERS / EudraVigilance) | ❌ |
| PA / claims platform (Cohere / AIM / TriZetto / Facets) | ❌ |
| ICD-10-CM / CPT coding reference (AHA Coding Clinic, CPT Assistant) | ❌ |
| ClinicalTrials.gov / sponsor EDC API | ❌ |
| MedWatch / EudraVigilance ICSR submission routing | ❌ |
| PHI de-identification pipeline (HIPAA Safe Harbor / Expert Determination) | ❌ |
| Append-only audit store (21 CFR Part 11 / CMS / OIG) | ❌ |
| Third-model clinical auditor cascade (ARIS §3.1) | ❌ |
| Human approval gate enforced in code | ❌ |
| PyPI pip-installable package | ❌ |

---

# Next Actions

| # | Action | Owner |
|---|---|---|
| 1 | Phase 2 workflow promotion — start with `PHIBreachScopeWorkflow` (veto) and `MentalHealthCrisisRiskWorkflow` (veto) | Engineering |
| 2 | EHR/EMR integration adapters (Epic / Cerner FHIR R4) | Engineering + Clinical Informatics |
| 3 | Live drug interaction DB integration (Lexicomp / Micromedex API) | Clinical Pharmacy + Engineering |
| 4 | InterQual / MCG clinical criteria integration | Payer Operations + Engineering |
| 5 | FDA FAERS / EudraVigilance integration for `prior_reports` field | Drug Safety + Engineering |
| 6 | MedWatch / EudraVigilance ICSR submission routing | Regulatory Affairs + Engineering |
| 7 | Dedicated third-model bias/contraindication auditor (ARIS §3.1) | Engineering |
| 8 | Tamper-evident audit store (21 CFR Part 11 / CMS / OIG) | Engineering + Compliance |
| 9 | Human approval gate enforced in code | Engineering |
| 10 | PyPI publish (pending credentials) | Engineering |
| 11 | SECURITY_MODEL.md healthcare deployment checklist (L-HEALTH-4 remediation) | Engineering + Compliance |
| 12 | 90-day shadow pilot per workflow class | Clinical Informatics + Payer Ops + Drug Safety + IRB |

---

<!-- _class: section -->

# Who It Is For

*Healthcare operations · Engineering · Researchers*

**Healthcare operations teams** evaluating LLM augmentation across the coding, payer, and clinical decision surface — prior auth, coding accuracy, discharge planning, drug interaction screening, adverse event triage. The convergence gates + veto channel + ledger provide a structured audit trail; per-workflow `PRODUCTION_GAPS` checklists name exactly what integration work is required before a pilot.

**Engineering teams** adding a new domain or scenario. Healthcare is the sixth reference implementation (after research + parole + retail + pc + industrial) and the first to apply the bias-gate pattern from parole to a clinical context. The recipe is locked: per-workflow `*Request` dataclass with `_MAX_FIELD_CHARS` cap, three domain-flag gates, optional veto via shared `extract_veto_directive`, helper-based flag extraction + claim registration + display truncation, `_DISCLAIMER` banner, approver checklist, skill templates with scenario-noun prefix.

**Researchers** studying cross-model adversarial pairs in patient-safety and regulatory-reporting decisions where ground truth is observable: coding audit accuracy at RAC/OIG review · PA denial overturn rates vs peer-to-peer outcome · drug interaction catch rate vs clinical pharmacist review · ADR causality accuracy vs qualified physician assessment · trial eligibility accuracy vs IRB audit · demographic bias reduction in eligibility decisions (JAMA 2019 Duma et al. baseline).

---

<!-- _class: lead -->

*Reference implementation:* `github.com/gmanch94/adv-multi-agent`

&nbsp;

*MVP-8 shipped:* diagnosis_code_audit · discharge_planning_risk · prior_authorization_review · claims_appeal_review
*drug_interaction_flagging · adverse_event_triage · treatment_plan_review · clinical_trial_eligibility*

&nbsp;

*19 Phase-2 workflow designs locked. M-HEALTH-1 + L-HEALTH-1..4 closed same-day. 6 audit cycles, 0 open findings.*

&nbsp;

*Adversarial multi-agent collaboration · Cross-family reviewer · Convergence gates · Veto channel · Bias-gate pattern*
*Teaching / research — not for production deployment*

&nbsp;

---

*Yang, R., Li, Y., & Li, S. (2026). ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration. arXiv:2605.03042. Shanghai Jiao Tong University · Shanghai Innovation Institute.*

*Duma, N., Vera Aguilera, J., Paludo, J., et al. (2019). Representation in Clinical Trials: A Renewed Call to Action. Mayo Clinic Proceedings (published via JAMA Network). doi:10.1016/j.mayocp.2019.08.009.*
