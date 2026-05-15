---
marp: true
theme: adv-slides
paginate: true
---

<!-- _class: lead -->

# Industrial Manufacturing & IoT
## Adversarial Multi-Agent across 8 OEM Workflows

Make-vs-Buy · Supplier · ECO · Quality · Product Liability · Recall · Resilience · Telematics

&nbsp;

*Domain application of the adv-multi-agent library*
*Modelled on the Crown Equipment surface · May 2026*

&nbsp;

*Based on ARIS (Yang, Li, Li — SJTU + Shanghai Innovation Institute, arXiv:2605.03042)*

---

<!-- _class: section -->

# 1. Problem Context

*Why adversarial multi-agent for an industrial OEM?*

---

## The Four Properties

Industrial OEM decisions concentrate the four properties ARIS targets:

| Property | Industrial manifestation |
|---|---|
| **Irreversibility** | $50M plant capex commit · recall scope = every unit shipped that year · functional-safety re-cert (months) · supplier disqualification · ECO that breaks 50k field-installed units |
| **Regulator audit-trail** | OSHA 1904 recordable logs · CPSC § 15(b) substantial-product-hazard reports · ANSI/ITSDF B56.x + ISO 3691-4 functional-safety · EPA emissions · FCPA / customs / export-control · SEC warranty-reserve disclosure |
| **Asymmetric information** | Supplier knows financial stress before OEM · customer knows duty-cycle abuse before warranty claim · field service knows failure-mode patterns before reliability engineering |
| **Echo-chamber risk** | OEM engineering's "we always do it this way" precedent-bias · same-family LLMs replicate it · load-bearing on root-cause attribution + supplier disqualification |

> Cross-family reviewer is the safeguard.

---

## The Scale & Stakes Problem

Industrial decisions are lower-volume than retail but higher-stake per decision, on a longer reversal cycle:

| Decision | Frequency | Per-instance stake |
|---|---|---|
| Make-vs-buy boundary | Per component / per sourcing cycle | Years of capability erosion if outsourced wrong; IP-leak permanent |
| Supplier qualification | Per supplier-program | Single-source disqualification → line stop |
| Engineering change order | Per design iteration (high frequency) | Field-deployed product fleet × supersession risk |
| Quality incident root-cause | Per escape | Feeds product-liability + recall; "operator error" attribution masks design |
| Product-liability attribution | Per incident with injury | Recall trigger; punitive-damages exposure; OSHA / CPSC report |
| Recall scope | Per substantial-product-hazard event | Every unit shipped; CPSC 5-business-day clock; multi-jurisdiction |
| Supply-chain resilience | Per-commodity quarterly | Hidden Tier-2 single-source = total line stop on geopolitical event |
| Telematics anomaly triage | Continuous (24×7) | Wasted truck-roll vs missed thermal runaway / safety-system signal |

A confident-but-wrong LLM at this scale produces recall-class errors, design-defect-attribution gaps, hidden single-source claims, and operator-error attribution that masks engineering signal.

> Human review of every recommendation is required — but auditing the *recommendation engine* improves the human's leverage.

---

## The Cross-Model Solution

Two models from different families propose and challenge the same recommendation. Failures correlated within a model family are caught by the other:

```
industrial.*Request   (8 MVP variants across 4 tracks; 27 in the full catalog)
  │
  ▼
Executor (Claude Opus 4.7, adaptive thinking)
  │  produces evidence-grounded advisory brief
  ▼
Reviewer (GPT-4o — different family, multi-mandate)
  │  1. Quality audit                   (score 0–10)
  │  2. Domain audit                    (3 flag classes per workflow)
  │  3. Reviewer veto                   (2 workflows — irreversible-class decisions)
  ▼
score ≥ threshold AND zero domain flags AND no veto?
  YES → converged, return output
  NO  → executor revises (critique + flags injected)
         repeat until convergence or MAX_REVIEW_ROUNDS
```

**Convergence is a conjunction** — quality gate *and* every domain-flag class clear *and* (for veto-using workflows) no veto.

---

<!-- _class: section -->

# 2. Six Tracks · 27 Workflows · MVP-8 Cut

*D-IND-1 — Design-locked catalog, one cut shipped*

---

## The 27-workflow catalog

Six tracks; MVP-8 marked ✅. Phase-2 designs locked in the design doc.

| Track | MVP | Phase 2 |
|---|---|---|
| **Manufacturing Ops** (4 MVP / 3 Phase-2) | MakeVsBuy ✅ · SupplierQualification ✅ · EngineeringChangeOrder ✅ · QualityIncidentRootCause ✅ | CapacityPlanning · ProductionSchedule · ObsolescenceManagement |
| **Safety / Recall / Reserve** (2 MVP / 3 Phase-2) | ProductLiabilityRootCause ✅ (veto) · RecallScopeManufacturing ✅ (veto) | FunctionalSafetyCase (veto) · EHSIncident (veto) · WarrantyReserve |
| **Strategic Capital** (1 MVP / 3 Phase-2) | SupplyChainResilience ✅ | PlantSiting (veto) · CapexAllocation · SourcingTariff |
| **Industrial IoT** (1 MVP / 4 Phase-2) | TelematicsAnomalyTriage ✅ | PredictiveMaintenanceRUL · FleetUtilizationAdvisory · SubscriptionRenewal · DataRightsContract (veto) |
| **Automation Deployment** (0 MVP / 3 Phase-2) | — | AutomationROI · WarehouseLayoutAdvisory · AutomationCommissioning (veto) |
| **Service & Aftermarket** (0 MVP / 3 Phase-2) | — | FieldServiceDispatchAdvisory · PartsDemandForecast · ExtendedWarrantyPricing |

8 of 8 MVP triple-flag · 2 of 8 add reviewer veto. Non-veto bias is intentional — most industrial decisions are reversible until they reach the safety / recall / liability frontier.

---

## Why these 8 for MVP (D-IND-1)

| # | Workflow | Veto? | Why MVP |
|---|---|---|---|
| 1 | `MakeVsBuyWorkflow` | — | Anchors the in-house-OEM thesis (Crown's 85/15); smallest-but-most-strategic decision |
| 2 | `SupplierQualificationWorkflow` | — | Covers the externally-sourced 15%; pairs with #1 |
| 5 | `EngineeringChangeOrderWorkflow` | — | Highest-frequency design decision; reviewer-as-field-implication-scan is unambiguously useful |
| 6 | `QualityIncidentRootCauseWorkflow` | — | 8D / DMAIC; feeds #8 + #9 |
| 8 | `ProductLiabilityRootCauseWorkflow` | ✅ | Highest-criticality anchor; design-defect attribution is unambiguous veto rationale |
| 9 | `RecallScopeManufacturingWorkflow` | ✅ | Direct reuse of `retail.recall_scope` shape; CPSC § 15(b) regulator-notification angle |
| 15 | `SupplyChainResilienceWorkflow` | — | Crown's stated "insulate from logistics chokepoints" thesis; reviewer audits dual-source claims |
| 17 | `TelematicsAnomalyTriageWorkflow` | — | InfoLink anchor; demonstrates the IoT track is real, not aspirational |

Cross-domain reuse map: when an industrial scenario is better served by an existing workflow (`pc.ClaimsReserve` for forklift claims; `pc.CommercialUnderwriting` for Crown's GL; `pc.CyberUnderwriting` for InfoLink posture; `retail.supplier_brief` for Crown's *customers* qualifying Crown).

---

<!-- _class: section -->

# 3. Manufacturing Ops Workflows

*MakeVsBuy · Supplier · ECO · Quality*

---

## MakeVsBuyWorkflow

**Triple-flag, no veto.** The OEM's 85/15 in-house boundary decision.

**Request fields:** component_summary, internal_cost_basis, external_bid_summary, capability_evidence, ip_risk_context, strategic_constraints.

**Flag classes:**
- `COST FLAGS` — should-cost build-up gaps; external bid TCO normalisation
- `CAPABILITY FLAGS` — PPAP / Cpk / PFMEA / fixture-validation evidence vs hand-waving claims
- `IP-LEAK FLAGS` — process know-how / design IP / trade secret exposure + export-control overlay (EAR / ITAR / EU dual-use)

No veto — sourcing decisions are reversible at the next sourcing-review cycle.

**Skill templates (4):** `makebuy_should_cost_buildup`, `makebuy_external_bid_normalisation`, `makebuy_capability_evidence_audit`, `makebuy_ip_leak_screen`.

---

## SupplierQualificationWorkflow

**Triple-flag, no veto.** Onboarding / re-qualifying external suppliers for the 15%.

**Request fields:** supplier_summary, financial_signals, quality_evidence, capacity_and_continuity, sub_tier_and_geographic, proposed_qualification.

**Flag classes:**
- `FINANCIAL FLAGS` — audited-statement + third-party-rating (D&B / RapidRatings / Altman Z) + customer-concentration stress signals beyond "we have not heard of any issues" framing
- `QUALITY FLAGS` — IATF 16949 / ISO 9001 / AS9100 + PPAP + SCAR + escape-rate evidence
- `GEO-CONCENTRATION FLAGS` — Tier-2 distinctness + sanctions / export-control + political + natural-hazard

No veto — supplier qualification is reversible.

**Skill templates (4):** `supplier_financial_screen`, `supplier_quality_evidence_audit`, `supplier_geo_concentration_check`, `supplier_sub_tier_mapping`.

---

## EngineeringChangeOrderWorkflow

**Triple-flag, no veto.** ECO impact assessment for affected fleet + adjacent products + supplier tooling.

**Request fields:** change_summary, affected_part_numbers, f3_analysis (originator-claimed F/F/F), fmea_context, deployed_product_context, supplier_and_tooling_context.

**Flag classes:**
- `SUPERSESSION FLAGS` — form / fit / function rigour per affected P/N; supersession direction (one-way / two-way / not interchangeable); effectivity basis
- `FMEA-DELTA FLAGS` — PFMEA / DFMEA rows added / modified / retired; S/O/D + RPN delta
- `REGRESSION FLAGS` — deployed-product compatibility (firmware × old/new build); verification + validation + field-trial coverage

No veto — ECOs are reversible via rollback ECO.

**Skill templates (4):** `eco_supersession_analysis`, `eco_fmea_delta_check`, `eco_regression_test_plan`, `eco_service_bulletin_draft`.

---

## QualityIncidentRootCauseWorkflow

**Triple-flag, no veto.** 8D / DMAIC investigation — feeds product-liability + recall.

**Request fields:** incident_summary, evidence_inventory, initial_causal_hypothesis, containment_scope, process_and_design_context, adjacent_products.

**Flag classes:**
- `CAUSAL-CHAIN FLAGS` — 5-Why anchored on evidence (SPC, MSA, teardown, serial-trace); reviewer rejects "operator error" attribution that masks design-defect or process-control gaps
- `CONTAINMENT FLAGS` — scope coverage matrix (WIP / FG / in-transit / DC / field) + sort-method capability
- `SYSTEMIC FLAGS` — adjacent products / platforms / shared tooling / shared supplier read-across; PFMEA RPN update

Escalation to product-liability / recall workflows is handled downstream.

**Skill templates (4):** `quality_five_why_construction`, `quality_containment_scope_check`, `quality_systemic_readacross`, `quality_pfmea_delta`.

---

<!-- _class: section -->

# 4. Safety / Recall / Reserve Workflows

*ProductLiabilityRootCause · RecallScopeManufacturing — both veto*

---

## ProductLiabilityRootCauseWorkflow

**Veto + triple-flag.** Tipover / pedestrian-strike / mechanical-failure attribution — bridges to `pc.ClaimsReserveWorkflow`.

**Request fields:** incident_summary, telematics_and_trace, equipment_configuration, standards_context, operator_and_training, field_failure_population, initial_attribution.

**Flag classes:**
- `DESIGN-DEFECT FLAGS` — foreseeable-misuse tolerance, standards comparison (ANSI/ITSDF B56.x / ISO 3691-x / OSHA 1910.178), field-failure-population pattern, adjacent-unit count
- `OPERATOR-ERROR FLAGS` — telematics / video / EDR / training-of-record evidence; reasonable-design test
- `WARNING-ADEQUACY FLAGS` — ANSI Z535 / HFE conspicuity + legibility + language + placement + manual concordance

**Veto criteria:** operator-error attribution where telematics / video / similar-unit pattern supports design-defect · foreseeable-misuse the design fails to tolerate · field-failure population non-random pattern with no design analysis · warning dismissed without evidence · catastrophic injury without parallel CPSC § 15(b) SPH analysis.

**Skill templates (4):** `prodliab_design_defect_screen`, `prodliab_operator_error_integrity`, `prodliab_warning_adequacy_audit`, `prodliab_standards_compliance_check`.

---

## RecallScopeManufacturingWorkflow

**Veto + triple-flag.** Mirrors `retail.recall_scope`; adds CPSC § 15(b) substantial-product-hazard mapping + OSHA + EU GPSR + Canada CCPSA notification routing.

**Request fields:** trigger_summary, evidence_inventory, fleet_serial_traceability, adjacent_product_exposure, regulatory_context, service_capacity_context, proposed_scope.

**Flag classes:**
- `TRIGGER-EVIDENCE FLAGS` — field-failure population credibility + CPSC SPH-tier mapping (death / serious-injury / unreasonable-risk / standard non-compliance / defect pattern)
- `FLEET-SCOPE FLAGS` — serial / build-date / configuration band; adjacent products sharing failure-mode-bearing component; pre-production exposure; international
- `REGULATORY-NOTIFY FLAGS` — CPSC § 15(b) 5-business-day clock + OSHA + NHTSA-equivalent + EU RAPEX/GPSR + state AG + country-specific

**Veto criteria:** substantial-product-hazard signal with narrow scope · field-failure pattern with affected band excluded · adjacent products with shared component excluded · regulator's published reportable-hazard criterion met but notification missing · CPSC § 15(b) "becomes aware" trigger with 5-day clock not addressed.

**Skill templates (4):** `recall_trigger_evidence_check`, `recall_fleet_scope_expansion`, `recall_regulatory_notification_map`, `recall_service_bulletin_draft`.

---

<!-- _class: section -->

# 5. Strategic Capital + IoT Workflows

*SupplyChainResilience · TelematicsAnomalyTriage*

---

## SupplyChainResilienceWorkflow

**Triple-flag, no veto.** "Insulate the supply chain" thesis — surfaces hidden Tier-2 single-source.

**Request fields:** commodity_summary, tier1_supplier_map, tier2_visibility, geographic_context, lead_time_and_route_context, inventory_and_buffer, incident_or_trigger.

**Flag classes:**
- `SINGLE-SOURCE FLAGS` — Tier-1 diverse but Tier-2 same (TSMC-class hidden single-source); active dual-source vs paper qualification; common-component single-point at Tier-N
- `GEO-CONCENTRATION FLAGS` — country + region + cluster + industrial-park overlay; political-risk + natural-hazard + logistics-chokepoint
- `LEAD-TIME-FRAGILITY FLAGS` — lead-time variance; route exposure (Panama / Suez / Malacca / Hormuz); modal substitution feasibility; buffer-policy implication

No veto — resilience-investment is program-level and reversible.

**Skill templates (4):** `supply_single_source_audit`, `supply_geo_cluster_mapping`, `supply_lead_time_variance_check`, `supply_buffer_policy_recommendation`.

---

## TelematicsAnomalyTriageWorkflow

**Triple-flag, no veto.** InfoLink-class anomaly → maintenance / service / safety brief.

**Request fields:** asset_summary, signal_payload, duty_cycle_baseline, recent_service_history, customer_contract_context, parts_and_service_network, initial_recommendation.

**Flag classes:**
- `SIGNAL-EVIDENCE FLAGS` — magnitude / duration / σ-from-baseline / detector confidence / corroborating-signals; reject single-reading alerts framed as actionable
- `FALSE-POSITIVE-COST FLAGS` — base rate + cost of wasted truck-roll vs cost of inaction (downtime / escalation / safety)
- `ACTIONABILITY FLAGS` — specific action + verified parts + priority tier + escalation threshold; reject vague "investigate further" outputs

No veto — telematics triage is operational; life-safety veto class belongs upstream (`ProductLiabilityRootCause` / `Recall`).

**Skill templates (4):** `telematics_signal_strength_audit`, `telematics_false_positive_analysis`, `telematics_action_recommendation`, `telematics_digital_twin_compare`.

---

<!-- _class: section -->

# 6. Convergence Patterns

*Triple-flag · Reviewer-veto · Audit-trail-first*

---

## Triple-flag gate (8 of 8 MVP workflows)

All 8 MVP workflows use the uniform dict-iteration pattern:

```python
_FLAG_HEADERS: tuple[str, ...] = (
    "COST FLAGS:",
    "CAPABILITY FLAGS:",
    "IP-LEAK FLAGS:",
)

current: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}
accumulated: dict[str, list[str]] = {h: [] for h in _FLAG_HEADERS}

for round_num in range(1, max_rounds + 1):
    ...
    for header in _FLAG_HEADERS:
        current[header] = extract_flags(critique, header)        # REASSIGN per round
        accumulated[header].extend(current[header])              # audit-trail accrues

    if review.approved and not any(current.values()):            # convergence gate
        converged = True
        break
```

- `current` is **reassigned** per round → no cross-round leakage
- `accumulated` is **appended** → audit-trail keeps every flag ever raised
- `any(current.values())` returns False iff every per-header list is empty → conjunction-gate

Veto workflows use the explicit-arg variant (3 lists vs 1 dict) — same semantics, more readable for the veto interleave.

---

## Reviewer-veto pattern (2 of 8 MVP workflows)

Veto-using workflows extend the gate with an independent halt channel:

```python
# Audit-trail writes happen BEFORE the veto check.
self.wiki.add_feedback(
    sanitize_for_prompt(review.critique, max_chars=max_wiki_chars),
    round_num=round_num,
    score=score,
)

veto_reason = self._extract_veto(review.critique, max_wiki_chars)
if veto_reason is not None:
    break        # halt before convergence check

if (
    review.approved
    and not current_design_flags
    and not current_operator_flags
    and not current_warning_flags
):
    converged = True
    break
```

**Audit-trail before veto break** — the vetoed round still writes the reviewer critique to the wiki + claims to the ledger. CPSC discovery defensibility requires it.

**Veto banner inserted into output** — output is `draft + VETO_BANNER + DISCLAIMER`. The draft is **not replaced** so the human can review what the executor proposed.

---

## Veto-criteria specificity

| Workflow | Veto trigger examples |
|---|---|
| `ProductLiabilityRootCauseWorkflow` | Operator-error attribution where telematics / similar-unit pattern supports design-defect · foreseeable-misuse the design fails to tolerate · non-random field-failure pattern with no design analysis · catastrophic injury without parallel CPSC § 15(b) SPH analysis |
| `RecallScopeManufacturingWorkflow` | Substantial-product-hazard signal with narrow scope · field-failure pattern with affected band excluded · adjacent products with shared component excluded · CPSC § 15(b) "becomes aware" 5-business-day clock not addressed |

> The veto channel is reserved for decisions where the cost of one more loop iteration before halting exceeds the cost of a false-positive halt. Most industrial decisions are reversible — only design-defect attribution + under-scoped recall cross that threshold.

---

<!-- _class: section -->

# 7. Security Model

*H-IND-1 + L-IND-1..5 — findings + remediation*

---

## Focused security sweep (2026-05-14)

Audit on the new 8-workflow industrial surface + shared `core/_internal.py` helpers:

| Severity | Count |
|---|---|
| CRITICAL | 0 |
| HIGH | **1** (H-IND-1) — **CLOSED same-session** |
| MEDIUM | 0 |
| LOW | 5 (L-IND-1..5) — L-IND-1 closed by H-IND-1 fix; rest backlogged |
| INFO / CLEAN | 16 validations confirmed |

Report: `docs/security-audits/2026-05-14-industrial-sweep.md`.

---

## H-IND-1 — Hyphenated FLAGS-header sibling-stop failure

**Vector.** `core/_internal.py` sibling-stop test `lhs.replace(" ", "").isalpha() and lhs.isupper()` rejects hyphens. Industrial flag headers heavily use hyphens (`DESIGN-DEFECT`, `IP-LEAK`, `FMEA-DELTA`, `OPERATOR-ERROR`, `TRIGGER-EVIDENCE`, `FLEET-SCOPE`, `REGULATORY-NOTIFY`, `SINGLE-SOURCE`, `GEO-CONCENTRATION`, `LEAD-TIME-FRAGILITY`, `SIGNAL-EVIDENCE`, `FALSE-POSITIVE-COST`, `CAUSAL-CHAIN`). Sibling-stop fails → `extract_flags` slurps subsequent sections into the prior list.

**Impact.** Convergence gate breaks (always >0 flags). Audit metadata misattributes flags across categories. Re-injection prompt drift. Affects **all 8 industrial workflows** + latent in 3 existing PC workflows (`environmental_impairment` KNOWN-CONDITION, `gig_platform_liability` COVERAGE-GAP, `parametric_crop` PERIL-MATCH).

**Why HIGH not CRITICAL.** No disclaimer suppression, no veto-banner bypass, no PII leak. Degrades correctness + corrupts audit field; "advisory-only" posture and safety-committee escalation path intact.

**Karpathy convention-level error.** The previous M-PC-1 audit closed the *opening* anchor; never audited the *closing* sibling-stop on hyphenated peers. Single shared parser, multiple domains drift together.

---

## H-IND-1 remediation

One regex change closes it for every existing + future domain:

```python
# _SIBLING_HEADER_LHS_RE accepts uppercase letters, spaces, and hyphens
# in the LHS; rejects digits, mixed-case, punctuation.
_SIBLING_HEADER_LHS_RE = re.compile(r"^[A-Z][A-Z\s\-]*[A-Z]$|^[A-Z]$")

def _is_sibling_header_lhs(lhs: str) -> bool:
    return bool(_SIBLING_HEADER_LHS_RE.match(lhs))
```

Replaces sibling-stop check in both `extract_flags` and `extract_veto_directive` continuation loop. **L-IND-1 closes simultaneously** (veto continuation also accepts hyphenated peer headers).

5 regression tests added:
- `TestExtractFlagsHyphenSiblingStop` — 4 cases covering hyphenated peers, three-section bleed, single-char header edge
- `test_sibling_header_check_stops_on_hyphenated_header` — veto continuation regression

481 tests pass (476 prior + 5 new). ruff + mypy clean.

---

## L-IND-2..5 — Defence-in-depth backlog

| Finding | Status |
|---|---|
| **L-IND-2** Pre-veto round-1 draft preserved via ledger + wiki, not in `WorkflowResult.output` | Backlog — add `metadata['first_draft']` to surface what's already preserved |
| **L-IND-3** `_format_flag_section` banner gating verified correct (no fix, documented) | CLOSED — documented for completeness |
| **L-IND-4** `bundled_skills_path` accepts arbitrary domain string | Backlog — allowlist `{research, parole, retail, pc, industrial}` |
| **L-IND-5** Per-field 1500-char silent truncation | Backlog — documented behaviour; add warning when truncation actually fires |

CRITICAL / HIGH workstreams: zero. Pre-merge gate cleared.

---

## What audit-defensible deployment requires

The library is teaching-grade by stated posture. Hardening for production requires (from `PRODUCTION_GAPS` in each module docstring):

1. **PLM / ERP / MES / CMMS / FRACAS integration** — Teamcenter / Windchill / Aras / SAP / Oracle EBS. Replace free-text inputs.
2. **Structured supplier-risk + standards feeds** — D&B / RapidRatings / Resilinc; ANSI / ITSDF B56.x / ISO 3691-x / IEC 61508 corpus.
3. **Telematics platform integration** — InfoLink / Hyster Tracker / Linde connect: structured signal stream.
4. **Regulator notification routing** — CPSC § 15(b) / OSHA / EU GPSR / Canada CCPSA structured submission, not checklist line items.
5. **Tamper-evident audit store** — CPSC / OSHA / product-liability discovery-defensible.
6. **Third-model auditor cascade (ARIS §3.1)** — separately configured model for veto-using workflows.
7. **Human approval gate enforced in code** — CAPA / ECN / recall / dispatch must not auto-publish.

---

<!-- _class: section -->

# 8. Shared Infrastructure

*Helpers in core/_internal.py · BaseWorkflow contract*

---

## Shared helpers (cross-workflow contract)

| Helper | Purpose | Used by industrial |
|---|---|---|
| `sanitize_for_prompt` | Strip control chars + NFC + cap length | Every workflow, every text injection |
| `extract_flags` | Parse `*FLAGS:` section (M1 line-anchored + H-IND-1 hyphen-stop) | All 8 workflows |
| `extract_veto_directive` | Parse `REVIEWER VETO:` directive (M-PC-1 line-anchored + H-IND-1/L-IND-1 hyphen-stop) | ProductLiability + Recall |
| `truncate_flag_display` | Cap re-injection at 16 entries with marker | All 8 `_format_flag_section` |
| `_register_claims` | Line-anchored `## Claims` split; 200-claim cap; dedup | All 8 (inherited from `BaseWorkflow`) |
| `parse_first_json` | Safe JSON extraction (no greedy DOTALL) | Reviewer output parsing |
| `coerce_score` | Clamp [0,10], reject NaN/inf | Reviewer score |
| `atomic_write_text` | Tempfile + fsync + replace | Ledger + Wiki persistence |
| `redact_secret` | Fixed-shape API-key redaction | Logging |

Each helper centralises an invariant. The H-IND-1 fix demonstrated the value of helper-level sharing: one regex change closed a HIGH across 8 industrial workflows + 3 latent-bug PC workflows simultaneously.

---

## BaseWorkflow contract

All 8 industrial workflows extend `BaseWorkflow` — same contract as research / parole / retail / pc:

```python
class BaseWorkflow(ABC):
    def __init__(self, config, executor=None, reviewer=None,
                 ledger=None, wiki=None) -> None: ...

    @abstractmethod
    async def run(self, **kwargs: Any) -> WorkflowResult: ...

    def _register_claims(self, output: str, round_num: int) -> None: ...
```

**No domain base class** (D-RETAIL-2 → D-RETAIL-7 → D-PC-3 → D-IND-1).
16 retail + 7 PC + 8 industrial workflows surveyed: per-flag-header banner / metadata key / checklist text diverge enough that base-class extraction costs more than it saves. Helper-level sharing is the right unit.

---

<!-- _class: section -->

# 9. Status

*8 of 8 MVP shipped · 481 tests · H-IND-1 closed*

---

## Build status

| Component | Status |
|---|---|
| 8 MVP workflows (Mfg Ops × 4 / Safety × 2 / Strategic × 1 / IoT × 1) | ✅ |
| 32 industrial skill templates (4 per workflow) | ✅ |
| 8 industrial examples (`examples/industrial/*.py`) | ✅ |
| Triple-flag pattern (8 of 8 MVP) | ✅ |
| Reviewer-veto pattern (2 of 8 MVP) | ✅ |
| 67 industrial unit tests across 8 files | ✅ all passing |
| **481 total tests** (research + parole + retail + pc + industrial + shared) | ✅ all passing |
| ruff + mypy clean | ✅ |
| D-IND-1 decision row in `decisions.md` | ✅ |
| Design doc (`docs/superpowers/specs/2026-05-14-industrial-domain-design.md`) | ✅ — full 27-workflow catalog with MVP-8 marked |
| Focused security sweep | ✅ — H-IND-1 + L-IND-1 closed; L-IND-2..5 LOW backlog |
| 19 Phase-2 workflow designs locked | ✅ |

---

## Production gaps (PRODUCTION_GAPS — per module)

| Integration | Status |
|---|---|
| PLM (Teamcenter / Windchill / Aras) | ❌ |
| ERP (SAP / Oracle EBS / IFS) | ❌ |
| MES + CMMS + FRACAS | ❌ |
| Telematics platform (InfoLink / Hyster Tracker / Linde connect:) | ❌ |
| Should-cost engine (activity-based costing) | ❌ |
| D&B / RapidRatings / Resilinc supplier-risk feed | ❌ |
| Standards library (ANSI/ITSDF B56.x / ISO 3691-x / OSHA 1910.178) | ❌ |
| CPSC § 15(b) / OSHA / EU GPSR / CCPSA notification routing | ❌ |
| Customs / export-control screening | ❌ |
| Append-only audit store (CPSC / OSHA discovery-defensible) | ❌ |
| Third-model auditor cascade (ARIS §3.1) | ❌ |
| Human approval gate enforced in code | ❌ |

The PRODUCTION_GAPS list per workflow makes each integration explicit so a downstream consumer can scope it.

---

## Phase 2 candidates (19 deferred — see catalog)

Highest-likely-first promotion order:

| # | Workflow | Trigger to promote |
|---|---|---|
| 10 | `FunctionalSafetyCaseWorkflow` (veto) | DualMode / AGV cert work load |
| 18 | `PredictiveMaintenanceRULWorkflow` | After observing #17 telematics-triage convergence |
| 24 | `AutomationCommissioningWorkflow` (veto) | After #10 is in tree |
| 26 | `PartsDemandForecastWorkflow` | After retail-parity refactor of `demand_signal` shape |
| 13 | `PlantSitingWorkflow` (veto) | Board-level capex review trigger |
| 21 | `DataRightsContractWorkflow` (veto) | GDPR / CCPA / state IoT-law update |

Designs are locked; promotion is a fill-in, not a re-design.

---

## Next actions (in priority order)

| # | Action | Owner |
|---|---|---|
| 1 | Commit + push pending — security audit closed | Engineering — this session |
| 2 | Retail-parity batch (L-PC-2/3/5 in 6 retail workflows) — still outstanding from prior session | Engineering — ~1 hr |
| 3 | Phase 2 workflow promotion (start with #10 FunctionalSafetyCase or #18 PredictiveMaintenanceRUL) | Engineering |
| 4 | PLM / ERP / MES / CMMS integration adapters | Engineering |
| 5 | Telematics platform integration (InfoLink / equivalents) | Service engineering + Engineering |
| 6 | Standards library + applicability engine | Product safety + Engineering |
| 7 | Regulator notification routing | Regulatory counsel + Engineering |
| 8 | Dedicated third-model auditor cascade | Engineering — ARIS §3.1 |
| 9 | Tamper-evident audit store | Engineering + Compliance |
| 10 | Human approval gate in code | Engineering |
| 11 | 90-day shadow pilot per workflow | Quality + Product Safety + Supply Chain + Service Engineering |

---

<!-- _class: section -->

# 10. Who It Is For

*Industrial OEM teams · Engineering · Researchers*

---

## Three audiences

**Industrial OEM teams** evaluating LLM augmentation across the decision surface — sourcing, supplier qualification, ECO impact, quality investigation, product-liability attribution, recall scope, supply-chain resilience, telematics triage. The convergence gates + veto channel + ledger provide a structured audit trail; per-workflow `PRODUCTION_GAPS` checklists name exactly what integration work is required before a pilot.

**Engineering teams** adding a new domain or scenario. Industrial is the fifth reference implementation (after research + parole + retail + pc) and the first organised as a 27-workflow design-locked catalog where the MVP is one explicit cut. Recipe locked: per-workflow `*Request` dataclass with `_MAX_FIELD_CHARS` cap, three domain-flag gates, optional veto via shared `extract_veto_directive`, helper-based flag extraction + claim registration + display truncation, `_DISCLAIMER` banner, approver checklist, skill templates with scenario-noun prefix.

**Researchers** studying cross-model adversarial pairs in irreversible / regulator-audited / asymmetric-info decisions where ground truth is observable: CAPA effectiveness at follow-up · recall scope adequacy at completion-rate review · supplier-qualification outcome at SCAR history · ECO regression at field-emergence · telematics-triage actionability at dispatch outcome · supply-chain resilience at disruption event · product-liability attribution at litigation outcome.

---

<!-- _class: lead -->

# Thank you

*Reference implementation:* `github.com/gmanch94/adv-multi-agent`

&nbsp;

*MVP-8 shipped:* make_vs_buy · supplier_qualification · engineering_change_order · quality_incident_root_cause
*product_liability_root_cause · recall_scope_manufacturing · supply_chain_resilience · telematics_anomaly_triage*

&nbsp;

*19 Phase-2 workflow designs locked. H-IND-1 + L-IND-1 closed same-session.*

&nbsp;

*Adversarial multi-agent collaboration · Cross-family reviewer · Convergence gates · Veto channel*
*Teaching / research — not for production deployment*
