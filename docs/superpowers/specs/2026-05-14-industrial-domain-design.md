# Industrial Manufacturing & IoT — Design Doc

Last updated: 2026-05-14 · refreshed post-ship 2026-05-14 PM
Status: **SHIPPED — 8 MVP workflows live on `main` at `e0b725a`. Security audit 2026-05-14 PM ([report](../../security-audits/2026-05-14-industrial-sweep.md)): 0 CRIT / 1 HIGH (H-IND-1) / 0 MED / 5 LOW (L-IND-1..5). H-IND-1 + L-IND-1 closed same-session via shared `_is_sibling_header_lhs` regex change in `core/_internal.py` (one regex, 8 industrial + 3 latent PC workflows inherit the fix). L-IND-2..5 remain LOW backlog. 19 Phase-2 workflow designs locked here for future fill-in.**

## Ship outcomes (post-design)

| Item | Outcome |
|---|---|
| Workflows live | 8 MVP (MakeVsBuy, SupplierQualification, EngineeringChangeOrder, QualityIncidentRootCause, ProductLiabilityRootCause [veto], RecallScopeManufacturing [veto], SupplyChainResilience, TelematicsAnomalyTriage) |
| Veto-using | 2 of 8 (ProductLiabilityRootCause, RecallScopeManufacturing) — matches design |
| Skill templates | 32 (4 per workflow) |
| Tests | 67 industrial unit tests + 5 H-IND-1 regression tests in `test_extract_flags.py` / `test_extract_veto_directive.py` |
| Audit findings closed | **H-IND-1** — `_is_sibling_header_lhs` regex now accepts hyphens (`^[A-Z][A-Z\s\-]*[A-Z]$|^[A-Z]$`); covers DESIGN-DEFECT, IP-LEAK, KNOWN-CONDITION, COVERAGE-GAP, PERIL-MATCH, FMEA-DELTA, OPERATOR-ERROR, TRIGGER-EVIDENCE, FLEET-SCOPE, REGULATORY-NOTIFY, SINGLE-SOURCE, GEO-CONCENTRATION, LEAD-TIME-FRAGILITY, SIGNAL-EVIDENCE, FALSE-POSITIVE-COST, CAUSAL-CHAIN. **L-IND-1** — closed alongside H-IND-1 via same regex change. |
| Open backlog (LOW) | L-IND-2 (surface `metadata['first_draft']` for vetoed workflows — regulator defensibility), L-IND-4 (allowlist `bundled_skills_path(domain)` arg), L-IND-5 (warn when per-field 1500-char silent truncation fires) |
| Karpathy lesson | Convention-level error compounding identified **twice** in shared parser: M-PC-1 (opening-anchor) and H-IND-1 (closing-sibling-stop). Both closed via shared-helper hoisting — one regex, every domain inherits. Next new naming convention (digit / slash / punctuation in headers) must re-audit `_is_sibling_header_lhs`. |
| Phase 2 status | 19 workflows locked-design, not built. Likely-first promotions: FunctionalSafetyCase [veto], PredictiveMaintenanceRUL, AutomationCommissioning [veto], PartsDemandForecast, PlantSiting [veto], DataRightsContract [veto]. |

---

Scope is **industrial manufacturing and hardware-enabled-software platforms**, modelled on the Crown Equipment Corporation surface (vertically-integrated lift-truck OEM with IoT telematics, automation, and aftermarket service). The pattern generalises to any discrete-manufacturing OEM that:

- designs and manufactures the majority of its own components (the "85% in-house" thesis),
- ships IoT-instrumented physical product on a subscription-data layer,
- deploys industrial automation under functional-safety regimes,
- carries an extended-lifecycle aftermarket-parts commitment.

Personal electronics, batch-process chemicals, FDA-regulated medical devices, and aerospace primes are explicitly **out of scope** for this domain — different invariants, different auditors. They are candidate future domains.

Package name: `industrial` (not `manufacturing`). Crown's framing — "hardware-enabled software platform" — is broader than the factory floor, and the IoT / automation / service workflows would be misfiled under `manufacturing/`.

---

## Why industrial fits the ARIS pattern

| Property | Industrial manifestation |
|---|---|
| Irreversibility | Capex commit ($50M+ plant), recall scope (every unit shipped that year), functional-safety certification (re-cert is months), supplier disqualification, ECO that breaks field-installed product. |
| Regulator audit-trail | OSHA recordables + 1904 logs, CPSC § 15(b) reports, NHTSA-equivalent for industrial trucks (ANSI/ITSDF B56.x), ISO 3691-4 for AGV/AMR, EPA emissions, FCPA / customs / export control, SEC disclosure on warranty reserves. |
| Echo-chamber risk | OEM engineering develops "we always do it this way" precedent-bias; same-family LLMs replicate it. Cross-family reviewer is the safeguard (D2 rationale) — particularly load-bearing on root-cause attribution and supplier-disqualification decisions. |
| Asymmetric info | Supplier knows their financial stress before OEM; customer knows duty-cycle abuse before warranty claim; field service knows failure-mode patterns before reliability engineering. Reviewer represents the "the other side reads this differently" check. |
| Veto class | Catastrophic-injury root-cause that points to design-defect (recall triggering), automation commissioning over an inadequate hazard analysis (functional-safety re-cert + liability), data-rights clause that gives away telematics data ownership (irreversible at scale). |

---

## Convention (inherited from retail / P&C)

Every industrial workflow MUST mirror the established convention — there is **no shared industrial base class** (D-RETAIL-2 → D-RETAIL-7 → D-PC-1 precedent):

1. Define a `*Request` dataclass with `to_prompt_text()`, every field capped at `_MAX_FIELD_CHARS = 1500`.
2. Sanitize all request text via `sanitize_for_prompt` at the workflow boundary (6000-char post-concat cap).
3. Loop up to `config.max_review_rounds`; convergence = `review.approved AND not current_flags AND not veto` (veto only for workflows that use it).
4. Register `## Claims` lines via `BaseWorkflow._register_claims` (inherits L1 cap = 200 claims/round).
5. Add reviewer critique to `self.wiki.add_feedback`.
6. Extract per-class flag lists via `extract_flags(critique, header)` (inherits L2 cap + M1 anchoring).
7. Veto-using workflows: delegate `_extract_veto` to `core._internal.extract_veto_directive` (M-PC-1). Include L-PC-2 FORMAT NOTE in criteria.
8. Triple-flag workflows: call `truncate_flag_display` in `_format_flag_section` (L-PC-5).
9. Build a `_build_*_checklist` listing human-action items (QE sign-off, safety officer sign-off, plant manager review, legal review).
10. Return `WorkflowResult` with output suffixed by `_DISCLAIMER`, metadata including flag list, checklist, `ledger_summary`, and (if veto) `veto_reason`.
11. PRODUCTION_GAPS docstring naming the live integrations a deployment would require (PLM / Teamcenter, ERP / SAP, MES, CMMS, telematics platform [Crown InfoLink / Hyster Tracker / Linde connect:], OSHA recordables system, supplier portal).
12. Cite ARIS in the module docstring.

Skill templates: flat under `src/adv_multi_agent/industrial/skills/templates/`, prefixed with the scenario noun (`makebuy_*`, `supplier_*`, `quality_*`, `eco_*`, `prodliab_*`, `recall_*`, `supply_*`, `telematics_*`).

Example files: one per scenario at `examples/industrial/<scenario>.py`, synthetic data only.

---

## Full workflow catalog (27 workflows · 6 tracks)

Legend: **MVP** = builds in the first sprint (parity with P&C's 7-workflow first pass + recall reuse). **Phase 2** = deferred to a later sprint, design recorded here so a future build is a fill-in not a re-design. **Veto** = uses the reviewer-veto pattern.

### Track 1 — Manufacturing Ops (core)

| # | Workflow | Flag classes | Veto | Status | Why this fits |
|---|---|---|---|---|---|
| 1 | `MakeVsBuyWorkflow` | `COST`, `CAPABILITY`, `IP-LEAK` | — | **MVP** | The 85/15 in-house boundary is the OEM's strategic spine; LLMs anchor on cost-only and miss IP-leak / capability-erosion. |
| 2 | `SupplierQualificationWorkflow` | `FINANCIAL`, `QUALITY`, `GEO-CONCENTRATION` | — | **MVP** | Onboarding external suppliers for the 15%; reviewer challenges supplier-financial-stress signals an executor's "checks pass" summary would gloss. |
| 3 | `CapacityPlanningWorkflow` | `DEMAND-FORECAST`, `BOTTLENECK`, `OVERTIME` | — | Phase 2 | Line capacity vs forecasted mix — strong but overlaps with `retail.demand_signal` shape; build after observing MVP convergence behaviour. |
| 4 | `ProductionScheduleWorkflow` | `SEQUENCE`, `CHANGEOVER`, `DUE-DATE` | — | Phase 2 | Daily / weekly line-balancing — high-frequency operational; advisory ROI thinner than strategic workflows. |
| 5 | `EngineeringChangeOrderWorkflow` | `SUPERSESSION`, `FMEA-DELTA`, `REGRESSION` | — | **MVP** | ECO impact is where "convention-level error compounding" lives — one design change breaks 100 deployed units; reviewer scans for field implications the originator forgets. |
| 6 | `QualityIncidentRootCauseWorkflow` | `CAUSAL-CHAIN`, `CONTAINMENT`, `SYSTEMIC` | — | **MVP** | 8D / DMAIC investigation — feeds product-liability + recall workflows; reviewer challenges "operator error" attribution that masks design defect. |
| 7 | `ObsolescenceManagementWorkflow` | `LAST-BUY`, `REDESIGN`, `LIFECYCLE-COMMITMENT` | — | Phase 2 | Long-tail parts decisions for extended-lifecycle promise — strong fit but lower frequency than MVP set. |

### Track 2 — Safety, Recall & Reserve (high-criticality)

| # | Workflow | Flag classes | Veto | Status | Why this fits |
|---|---|---|---|---|---|
| 8 | `ProductLiabilityRootCauseWorkflow` | `DESIGN-DEFECT`, `OPERATOR-ERROR`, `WARNING-ADEQUACY` | ✅ | **MVP** | Tipover / pedestrian-strike attribution; the veto fires when design-defect signal is present but draft attributes to operator. Bridges to `pc.ClaimsReserveWorkflow`. |
| 9 | `RecallScopeManufacturingWorkflow` | `TRIGGER-EVIDENCE`, `FLEET-SCOPE`, `REGULATORY-NOTIFY` | ✅ | **MVP** | Direct reuse of `retail.recall_scope` shape (D-RETAIL-1). Veto for `should-recall but draft scopes narrow`. CPSC § 15(b) / OSHA notification. |
| 10 | `FunctionalSafetyCaseWorkflow` | `HAZARD-COVERAGE`, `SIL-EVIDENCE`, `OPERATIONAL-LIMIT` | ✅ | Phase 2 | ISO 3691-4 / IEC 61508 / ANSI B56.5 certification package for DualMode / AGV. High value but cert work is months of human-SME loop; LLM advisory ROI is narrower. |
| 11 | `EHSIncidentWorkflow` | `OSHA-RECORDABILITY`, `ROOT-CAUSE`, `SYSTEMIC` | ✅ | Phase 2 | OSHA recordable investigation; overlaps Track 1 #6 with regulator-reporting angle. Build after observing #6 patterns. |
| 12 | `WarrantyReserveWorkflow` | `FAILURE-RATE`, `SEVERITY`, `TREND` | — | Phase 2 | Warranty $ accrual — actuarial overlap with `pc.ClaimsReserveWorkflow`; likely better as a Phase 2 specialization or domain-cross reference. |

### Track 3 — Strategic Capital

| # | Workflow | Flag classes | Veto | Status | Why this fits |
|---|---|---|---|---|---|
| 13 | `PlantSitingWorkflow` | `LABOR-MARKET`, `TARIFF-REGIME`, `ENERGY-RELIABILITY`, `GEOPOLITICAL` | ✅ | Phase 2 | New plant siting (OH/NC/DE/CN type decision). Veto on single-point-of-failure geo concentration. Board-level decision — quarterly cadence not weekly. |
| 14 | `CapexAllocationWorkflow` | `ORGANIC-VS-MA`, `ROIC`, `CYCLE-PHASE` | — | Phase 2 | Build vs buy vs return capital. Smaller LLM-augmentation surface; finance teams have models. |
| 15 | `SupplyChainResilienceWorkflow` | `SINGLE-SOURCE`, `GEO-CONCENTRATION`, `LEAD-TIME-FRAGILITY` | — | **MVP** | Logistics-chokepoint exposure (Crown's stated "insulate supply chain" thesis). Reviewer challenges "we have a second source" claims that aren't actually dual-sourced at the sub-tier. |
| 16 | `SourcingTariffWorkflow` | `DUTY-CLASSIFICATION`, `FTA-ELIGIBILITY`, `TRANSFER-PRICING` | — | Phase 2 | USMCA / EU / CN routing — specialist customs surface, narrower applicability than #15. |

### Track 4 — Industrial IoT / Telematics / SaaS (InfoLink-class)

| # | Workflow | Flag classes | Veto | Status | Why this fits |
|---|---|---|---|---|---|
| 17 | `TelematicsAnomalyTriageWorkflow` | `SIGNAL-EVIDENCE`, `FALSE-POSITIVE-COST`, `ACTIONABILITY` | — | **MVP** | InfoLink-style shock / battery / utilization alert → maintenance brief. Anchors the IoT track. Reviewer challenges weak-signal alerts that would waste a truck-roll. |
| 18 | `PredictiveMaintenanceRULWorkflow` | `MODEL-CONFIDENCE`, `SURVIVORSHIP-BIAS`, `DATA-SUFFICIENCY` | — | Phase 2 | Remaining-useful-life on battery / drive unit. Strong but specialist; build after observing #17. |
| 19 | `FleetUtilizationAdvisoryWorkflow` | `UTILIZATION-MEASUREMENT`, `RIGHTSIZING`, `CONTRACT-TERMS` | — | Phase 2 | Customer-fleet right-sizing brief. Commercial workflow — touches sales loop more than engineering. |
| 20 | `SubscriptionRenewalWorkflow` | `CHURN-SIGNAL`, `PRICE-ELASTICITY`, `FEATURE-USE` | — | Phase 2 | InfoLink renewal pricing + retention. B2B-SaaS playbook; existing tooling competes with adversarial workflow. |
| 21 | `DataRightsContractWorkflow` | `OWNERSHIP`, `GDPR-CCPA`, `DOWNSTREAM-USE` | ✅ | Phase 2 | Telematics data-use clauses. Veto on GDPR / CCPA / state-IoT-law landmines. High value but legal-review workflow shape; build after observing IoT track patterns. |

### Track 5 — Automation Deployment (Specialty)

| # | Workflow | Flag classes | Veto | Status | Why this fits |
|---|---|---|---|---|---|
| 22 | `AutomationROIWorkflow` | `LABOR-OFFSET`, `DOWNTIME-COST`, `RAMP-RISK` | — | Phase 2 | DualMode deployment business case. Strong fit but commercial-only; bundles with #19 / #20. |
| 23 | `WarehouseLayoutAdvisoryWorkflow` | `TRAFFIC-MIX`, `THROUGHPUT`, `SAFETY-SEPARATION` | — | Phase 2 | Mixed human/robot floorplan. Specialist; benefits from #10 functional-safety case first. |
| 24 | `AutomationCommissioningWorkflow` | `TEST-COVERAGE`, `FAILURE-MODE`, `GO-LIVE-GATE` | ✅ | Phase 2 | Site-acceptance test plan. Veto on incomplete hazard analysis. Pairs with #10. |

### Track 6 — Service & Aftermarket

| # | Workflow | Flag classes | Veto | Status | Why this fits |
|---|---|---|---|---|---|
| 25 | `FieldServiceDispatchAdvisoryWorkflow` | `SLA-RISK`, `SKILL-MATCH`, `ESCALATION` | — | Phase 2 | High-value technician routing. Real-time operational; advisory ROI thinner. |
| 26 | `PartsDemandForecastWorkflow` | `LONG-TAIL`, `SUBSTITUTION`, `OBSOLESCENCE-INTERSECT` | — | Phase 2 | Long-tail SKU demand. Direct reuse of `retail.demand_signal` skeleton with manufacturing parts mix; build after observing retail-parity backlog. |
| 27 | `ExtendedWarrantyPricingWorkflow` | `LOSS-RATIO`, `ADVERSE-SELECTION`, `RESERVE-ADEQUACY` | — | Phase 2 | Service-contract pricing — actuarial overlap with `pc.CommercialUnderwritingWorkflow`. Likely better as a cross-domain reuse than a new workflow. |

---

## MVP cut (8 workflows)

Decision: D-IND-1 (see `docs/decisions.md`).

| # | Workflow | Veto | Rationale |
|---|---|---|---|
| 1 | `MakeVsBuyWorkflow` | — | Anchors the in-house-OEM thesis; smallest-but-most-strategic decision. |
| 2 | `SupplierQualificationWorkflow` | — | Covers the externally-sourced 15%; pairs with #1. |
| 5 | `EngineeringChangeOrderWorkflow` | — | Highest-frequency design decision; reviewer-as-field-implication-scan is unambiguously useful. |
| 6 | `QualityIncidentRootCauseWorkflow` | — | Feeds #8 and #9; 8D / DMAIC is broadly understood. |
| 8 | `ProductLiabilityRootCauseWorkflow` | ✅ | Highest-criticality anchor; veto rationale (design-defect attribution) is unambiguous. |
| 9 | `RecallScopeManufacturingWorkflow` | ✅ | Direct reuse of `retail.recall_scope` shape; CPSC § 15(b) regulator-notification angle. |
| 15 | `SupplyChainResilienceWorkflow` | — | Crown's stated "insulate from logistics chokepoints" thesis; reviewer audits dual-source claims. |
| 17 | `TelematicsAnomalyTriageWorkflow` | — | InfoLink anchor; demonstrates IoT track is real, not aspirational. |

**Veto-using count:** 2 of 8 (vs P&C's 4 of 7). The non-veto bias is intentional — most industrial decisions are reversible (ECO can be revoked, supplier disqualified, automation pilot rolled back) until they reach the safety / recall / liability frontier.

**Out of MVP, deferred to Phase 2:** 19 workflows. Each row above is canonical; future builds fill in code against the locked design.

---

## Cross-domain reuse map

When an industrial scenario is better served by an existing domain workflow:

| Scenario | Use this existing workflow | Why |
|---|---|---|
| Crown's own GL / product / fleet bind | `pc.CommercialUnderwritingWorkflow` | The insurance side of the same decision surface. |
| Crown's cyber posture for InfoLink | `pc.CyberUnderwritingWorkflow` | InfoLink = cloud + telematics = direct fit. |
| Forklift-incident claim reserve | `pc.ClaimsReserveWorkflow` | Crown as insured / claim originator. |
| Crown's customers qualifying Crown as supplier | `retail.supplier_brief` | Direction-flip on the supplier-evaluation shape. |
| Industrial-parts demand seed | `retail.demand_signal` | Skeleton for #26 PartsDemandForecast when promoted. |
| Crown's customers forecasting warehouse demand | `retail.demand_signal` (direct) | Customer-side workflow, not Crown-side. |

---

## Security model — known concerns (to be confirmed by `/security-audit`)

By construction the industrial domain inherits all core security properties:

- `sanitize_for_prompt` strips control chars + braces at the workflow boundary.
- `_MAX_FIELD_CHARS = 1500` per field; 6000-char post-concat cap.
- `extract_flags` line-anchored (M1).
- `extract_veto_directive` line-anchored + section-stop + sibling-header (M-PC-1 / L5).
- `truncate_flag_display` caps re-injection at 16 (L-PC-5).
- `Skill.render` strips control + braces (L-PC-4 cross-domain fix).
- `_DISCLAIMER` injected in code, not from prompt.

Industrial-specific concerns to audit:

1. **Telematics signal payload injection** — `TelematicsAnomalyTriageWorkflow.signal_payload` is the highest-volume free-text field (anomaly descriptions from devices); confirm `_MAX_FIELD_CHARS` cap and `sanitize_for_prompt` apply uniformly.
2. **Supplier-name leak through `_register_claims`** — `SupplierQualificationWorkflow` claims may quote supplier financial-stress signals; confirm ledger does not propagate verbatim outside `metadata`.
3. **Product-liability draft preservation** — `ProductLiabilityRootCauseWorkflow` must preserve the *first* root-cause attribution if vetoed, not the revised one (regulator-defensible audit trail). Same shape as `ClaimsReserveWorkflow`.
4. **Recall-scope under-narrowing** — `RecallScopeManufacturingWorkflow` veto must fire on "VIN range too narrow" not just "should-recall". Cross-check with `retail.recall_scope` invariants.
5. **ECO prompt-injection via change-description** — engineers paste raw CAD-system change notes; confirm brace-stripping covers `{` patterns common in serialized PLM diff.

These will be enumerated in `docs/security-audits/2026-05-14-industrial-sweep.md` once the audit runs.

---

## PRODUCTION_GAPS (will appear in every workflow docstring)

The industrial domain's "what a deployment would need" list:

1. **PLM integration** (Teamcenter / Windchill / Aras) — `EngineeringChangeOrderWorkflow` consumes structured ECO records, not free-text.
2. **ERP integration** (SAP / Oracle EBS / IFS) — supplier financial-stress signals via D&B / RapidRatings; not analyst prose.
3. **MES integration** — `QualityIncidentRootCauseWorkflow` consumes structured non-conformance records.
4. **Telematics platform** — InfoLink / Hyster Tracker / Linde connect: — structured signal stream not paraphrased prose.
5. **Customer-quality feedback (CQF)** — `ProductLiabilityRootCauseWorkflow` field-failure mode evidence from CMMS / FRACAS, not narrative.
6. **OSHA recordables system** — CPSC § 15(b) / OSHA 300 integration for `RecallScopeManufacturingWorkflow` notification gates.
7. **Customs / trade-compliance system** — for #16 `SourcingTariffWorkflow` HTS classification, FTA eligibility.
8. **D&B / RapidRatings / Resilinc** — supplier financial-stress + geographic-concentration data.
9. **Append-only audit store** — tamper-evident for CPSC / OSHA defensibility (mirrors P&C SOX requirement).
10. **Human approval gate enforced in code** — recall trigger / ECO release / supplier disqualification must not auto-publish.
11. **Dedicated third-model engineering auditor cascade** — ARIS § 3.1 — separately configured model for veto-using workflows (ProductLiabilityRootCauseWorkflow + RecallScopeManufacturingWorkflow at MVP).

---

## Open questions (post-ship status)

1. **`FunctionalSafetyCaseWorkflow` (#10) MVP-jump?** — held Phase 2 at MVP ship; not yet prioritised. Re-evaluate when DualMode commercial messaging surfaces in a session.
2. **`WarrantyReserveWorkflow` (#12) vs `pc.ClaimsReserveWorkflow` reuse** — unresolved. Decide when Track 2 expands; cross-domain reference still preferred over duplicate workflow.
3. **`PartsDemandForecastWorkflow` (#26)** — still gated on retail parity (L-PC-2 / L-PC-3 / L-PC-5 cross-domain backlog). Land parity first to keep helpers consistent.

---

## Build sequence (8-workflow MVP)

```
MakeVsBuy (#1) — anchor strategic workflow, no veto, exercises shared helpers
   → SupplierQualification (#2) — pairs with #1, same shape
      → SupplyChainResilience (#15) — extends the supplier-risk surface
         → EngineeringChangeOrder (#5) — highest-frequency, exercises ECO field implications
            → QualityIncidentRootCause (#6) — feeds #8 and #9
               → ProductLiabilityRootCause (#8, veto) — first veto in this domain
                  → RecallScopeManufacturing (#9, veto) — closest analog to retail.recall_scope
                     → TelematicsAnomalyTriage (#17) — IoT track anchor

Per workflow: source → 4 skill templates → example → unit tests (mirrors test_claims_reserve.py shape).
```

After the 8th workflow lands and tests are green: focused `/security-audit` on the new surface, remediate, commit.

**Actual ship outcome:** the build sequence ran as planned. Security audit surfaced H-IND-1 (HIGH) — `extract_flags` / `extract_veto_directive` sibling-stop rejected hyphenated peer headers — which 67 industrial unit tests missed because every test used `any(substring in f for f in flags)` instead of list-equality. Closed same-session via one regex change in `core/_internal._is_sibling_header_lhs`; 5 regression tests added. Three latent PC workflows (CoverageDecision, EnvironmentalImpairment, GigPlatformLiability) inherited the fix automatically. Lesson: triple-flag list extractors must be tested with `assert flags == [...]` or `assert len(flags) == N`, never `any(...)`.
