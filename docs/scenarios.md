# Adversarial Multi-Agent — Scenario Tracker

Grouped by domain. Status: **built** | **planned** | **candidate**

---

## Research (`src/adv_multi_agent/research/`)
> Academic and scientific workflows

| Scenario | Status | Notes |
|---|---|---|
| Peer review loop | **built** | AutoReviewLoop — executor drafts, reviewer critiques |
| Idea discovery | **built** | IdeaDiscovery — novelty scoring, reviewer challenges overlap |
| Rebuttal generation | **built** | RebuttalWorkflow — reviewer stress-tests rebuttal arguments |
| Manuscript assurance | **built** | 3-stage verifier + 5-pass editor |

---

## Parole (`src/adv_multi_agent/parole/`)
> Criminal justice decision support

| Scenario | Status | Notes |
|---|---|---|
| Parole risk assessment | **built** | ParoleAssessmentWorkflow — bias-gate convergence, irreversible-decision pattern |

---

## Retail — Operations (`src/adv_multi_agent/retail/`)
> Store and supply chain operations

| Scenario | Status | Notes |
|---|---|---|
| Demand forecasting | **built** | DemandForecastWorkflow — ASSUMPTION FLAGS convergence gate; synthetic Kroger example |
| Labor scheduling | **built** | LaborSchedulingWorkflow — COMPLIANCE FLAGS convergence gate; synthetic Kroger example |
| Inventory replenishment | **built** | InventoryReplenishmentWorkflow — LEAD-TIME + STOCKOUT + CAPACITY flags; per-DC per-SKU PO schedule from demand forecast; synthetic Denver-DC dairy+shelf example |

---

## Retail — Commercial (`src/adv_multi_agent/retail/`)
> Pricing, supplier, and product decisions

| Scenario | Status | Notes |
|---|---|---|
| Promo / markdown optimization | **built** | PromoMarkdownWorkflow — ELASTICITY + MARGIN + TIMING flags; cannibalization-aware margin math; synthetic Memorial Day example |
| Supplier negotiation briefs | **built** | SupplierBriefWorkflow — BATNA + COST + RELATIONSHIP flags; cost-floor anchored in input-cost drivers; synthetic corrugated-packaging example |
| Private label product decisions | **built** | PrivateLabelWorkflow — CANNIBALIZATION + BRAND + SUPPLY flags; total-category-margin math incl. adverse case; co-manufacturer audit + capacity verification; synthetic Hearth Reserve coffee example |

---

## Retail — Customer (`src/adv_multi_agent/retail/`)
> Personalization and loyalty

| Scenario | Status | Notes |
|---|---|---|
| Loyalty / personalization offers | **built** | LoyaltyOfferWorkflow — FAIRNESS + MARGIN + GAMING flags; explicit allowed/disallowed attribute lists (parole bias-gate pattern applied commercially) |

---

## Retail — Safety & Compliance (`src/adv_multi_agent/retail/`)
> Irreversible or regulated decisions

| Scenario | Status | Notes |
|---|---|---|
| Food safety / recall scope | **built** | RecallScopeWorkflow — reviewer-veto gate (D-RETAIL-1); SCOPE + EVIDENCE flags; synthetic Listeria example |

---

## Property & Casualty (`src/adv_multi_agent/pc/`)
> Commercial insurance underwriting and claims

| Scenario | Status | Notes |
|---|---|---|
| Claims reserve estimation | **built** | ClaimsReserveWorkflow — reviewer-veto gate (D-PC-2); RESERVE + PRECEDENT + LITIGATION flags; SOX-auditable decision |
| Coverage & bad-faith assessment | **built** | CoverageDecisionWorkflow — COVERAGE + PROCEDURE + DENIAL flags; policy-language-anchored |
| Commercial underwriting | **built** | CommercialUnderwritingWorkflow — RISK + RATE + EXCLUSION flags; no veto (renewals are reversible) |
| Cyber risk assessment | **built** | CyberUnderwritingWorkflow — CONTROL + BREACH-HISTORY + ATTESTATION flags; control-gap anchored |
| Environmental impairment liability | **built** | EnvironmentalImpairmentWorkflow — reviewer-veto (D-PC-6); KNOWN-CONDITION + TAIL + REGULATORY-OVERLAP flags; CERCLA-anchored |
| Parametric crop insurance | **built** | ParametricCropWorkflow — PERIL-MATCH + BASIS + ATTACHMENT flags; no veto (commodity-futures-tied); synthetic corn-grower example |
| Gig platform liability | **built** | GigPlatformLiabilityWorkflow — reviewer-veto (D-PC-6); CLASSIFICATION + COVERAGE-GAP + REGULATORY-PATCHWORK flags; state-labor-law-anchored |

---

## Industrial Manufacturing & IoT (`src/adv_multi_agent/industrial/`)
> Manufacturing operations, safety, and supply chain

| Scenario | Status | Notes |
|---|---|---|
| Make vs. buy analysis | **built** | MakeVsBuyWorkflow — CAPEX + SUPPLY + QUALITY flags; financial-model-anchored |
| Supplier qualification | **built** | SupplierQualificationWorkflow — AUDIT + CAPACITY + RISK flags; audit-findings-anchored |
| Engineering change order review | **built** | EngineeringChangeOrderWorkflow — SAFETY + COST + SCHEDULE flags; functional-safety-re-cert-anchored |
| Quality incident root cause | **built** | QualityIncidentRootCauseWorkflow — ROOT + SCOPE + CORRECTIVE flags; FMEA-anchored |
| Product liability root cause | **built** | ProductLiabilityRootCauseWorkflow — reviewer-veto (D-IND-1); PROXIMATE + DESIGN + DUTY flags; SOX warranty-reserve-anchored |
| Recall scope (manufacturing) | **built** | RecallScopeManufacturingWorkflow — reviewer-veto (D-IND-1); SCOPE + EVIDENCE + CPSC flags; reuses retail.recall_scope shape |
| Supply chain resilience | **built** | SupplyChainResilienceWorkflow — CONCENTRATION + GEOPOLITICAL + FINANCIAL flags; Crown InfoLink telematics example |
| Telematics anomaly triage | **built** | TelematicsAnomalyTriageWorkflow — ANOMALY + PATTERN + RELIABILITY flags; InfoLink fleet-health-anchored |

---

## Healthcare (`src/adv_multi_agent/healthcare/`)
> Clinical decision support + payer operations + drug safety

| Scenario | Status | Notes |
|---|---|---|
| Diagnosis code audit | **built** | DiagnosisCodeAuditWorkflow — ACCURACY + COMPLIANCE + SPECIFICITY flags; ICD-10 code-selection-anchored |
| Discharge planning risk | **built** | DischargePlanningRiskWorkflow — READMISSION + CARE-GAP + SOCIAL-DETERMINANT flags; risk-stratification-anchored |
| Prior authorization review | **built** | PriorAuthorizationReviewWorkflow — MEDICAL-NECESSITY + COVERAGE + DOCUMENTATION flags; payer-policy-anchored |
| Claims appeal review | **built** | ClaimsAppealReviewWorkflow — EVIDENCE + COVERAGE + PROCEDURE flags; denial-rationale-anchored |
| Drug interaction flagging | **built** | DrugInteractionFlaggingWorkflow — reviewer-veto (D-HEALTH-1); SEVERITY + EVIDENCE + CONTRAINDICATION flags; FDA Orange Book + DrugBank-anchored |
| Adverse event triage | **built** | AdverseEventTriageWorkflow — reviewer-veto (D-HEALTH-1); SEVERITY + CAUSALITY + REGULATORY flags; FDA 7/15-day expedited-report-anchored; ICH E2A serious-unexpected ADR |
| Treatment plan review | **built** | TreatmentPlanReviewWorkflow — reviewer-veto (D-HEALTH-1); GUIDELINE + CONTRAINDICATION + RISK flags; clinical-practice-guideline-anchored |
| Clinical trial eligibility | **built** | ClinicalTrialEligibilityWorkflow — reviewer-veto + bias-gate (D-HEALTH-1); BIAS + ELIGIBILITY + EVIDENCE flags; parole bias-gate pattern applied clinically; JAMA 2019 demographic-bias anchored |

---

## Other Domains (future)

| Domain | Scenario | Status | Notes |
|---|---|---|---|
| Finance | Loan underwriting | candidate | Adversarial reviewer catches protected-class proxies |
| Finance | Fraud alert triage | candidate | Executor flags; reviewer challenges false-positive rate |
| Legal | Contract risk review | candidate | Executor summarizes risk; reviewer stress-tests omissions |
| HR | Performance review drafting | candidate | Bias-gate on protected attributes |

---

*Last updated: 2026-05-16*
