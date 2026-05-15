# Retail Domain Design Spec
*2026-05-13 — consolidated (initial 2 workflows + 6-workflow sweep)*

Status: **APPROVED — advisor 2026-05-13** (sweep blockers folded in: package-data, veto control flow, per-PR additions)

## Overview

New `retail/` domain alongside `parole/`, shipped in two waves:

- **Wave 1 (initial, 2 workflows):** demand forecasting + labor scheduling. Mirrors parole pattern exactly — no new abstractions.
- **Wave 2 (sweep, 6 workflows, 1 PR each, sequential):** recall scope (introduces reviewer-veto), loyalty/personalization, promo/markdown, supplier briefs, inventory replenishment, private label.

Final state: 8 retail workflows, 25 skill templates, 1 reviewer-veto pattern (recall).

Wave-1 ship order: parallel, single PR.
Wave-2 ship order:

1. **Food recall scope** — `RecallScopeWorkflow` (operations + safety, veto pattern)
2. **Loyalty/personalization offers** — `LoyaltyOfferWorkflow` (customer)
3. **Promo/markdown optimization** — `PromoMarkdownWorkflow` (commercial)
4. **Supplier negotiation briefs** — `SupplierBriefWorkflow` (commercial)
5. **Inventory replenishment** — `InventoryReplenishmentWorkflow` (operations)
6. **Private label product decisions** — `PrivateLabelWorkflow` (commercial)

---

## Structure (final)

```
src/adv_multi_agent/retail/
  __init__.py
  workflows/
    __init__.py
    demand_forecasting.py        # Wave 1
    labor_scheduling.py          # Wave 1
    recall_scope.py              # Wave 2 — veto pattern
    loyalty_offer.py             # Wave 2
    promo_markdown.py            # Wave 2
    supplier_brief.py            # Wave 2
    inventory_replenishment.py   # Wave 2
    private_label.py             # Wave 2
  skills/
    __init__.py
    templates/                   # flat, prefixed by scenario noun
      demand_*.md
      labor_*.md
      recall_*.md
      loyalty_*.md
      promo_*.md
      supplier_*.md
      replenishment_*.md
      private_label_*.md

examples/retail/
  __init__.py
  <one file per workflow>.py     # synthetic Request, runs workflow
```

---

## Wave 1 — initial 2 workflows

### Workflow 1: Demand Forecasting

**Input dataclass — `ForecastRequest`**

| Field | Type | Description |
|---|---|---|
| `store_id` | `str` | Store identifier (e.g. "KRO-OH-0042") |
| `sku` | `str` | SKU code |
| `product_category` | `str` | e.g. "dairy", "produce", "beverages" |
| `historical_sales` | `str` | Free-text: last 8 weeks units sold per week |
| `current_inventory` | `str` | On-hand units + in-transit units |
| `lead_time_days` | `str` | Supplier lead time in days |
| `upcoming_events` | `str` | Local events, holidays, promotions in next 4 weeks |
| `seasonality_notes` | `str` | Known seasonal patterns for this SKU/category |
| `weather_forecast` | `str` | 2-week weather outlook (temp, precipitation) |
| `unemployment_rate` | `str` | Local unemployment rate + trend (affects spend) |

**Executor task** — structured replenishment recommendation with sections: Demand Signal Analysis, Forecast (units/week, 4-week horizon), Replenishment Recommendation, Key Assumptions, Evidence Gaps, Claims (`[Source: <field>] <claim>`).

**Reviewer criteria** (score 0–10, weighted):
1. **Forecast Grounding** (30%) — anchored to historical signal? adjustments justified?
2. **Assumption Audit** (25%) — assumptions explicit, stated, proportionate? Flag under `ASSUMPTION FLAGS:`.
3. **Risk Balance** (25%) — stockout vs. overstock/spoilage tradeoff sound?
4. **Completeness** (10%) — data gaps noted? confidence appropriate?
5. **Actionability** (10%) — order recommendation specific (units, date, supplier)?

**Convergence:** score ≥ 7.5 **and** zero `ASSUMPTION FLAGS`.

**Production gaps:** live POS integration, ML demand baseline, supplier API, automated stockout/overstock cost, human buyer approval gate.

### Workflow 2: Labor Scheduling

**Input dataclass — `SchedulingRequest`**

| Field | Type | Description |
|---|---|---|
| `store_id` | `str` | Store identifier |
| `week_start` | `str` | ISO date of week start (Monday) |
| `projected_traffic` | `str` | Expected customer volume by day + peak hours |
| `staff_roster` | `str` | Names, roles, availability constraints, FT/PT status |
| `labor_budget` | `str` | Weekly labor budget in dollars |
| `local_events` | `str` | Events affecting foot traffic |
| `state_labor_law_notes` | `str` | Minor labor, overtime threshold, break requirements |
| `unemployment_rate` | `str` | Local unemployment rate + trend |

**Executor task** — weekly schedule with sections: Schedule (day-by-day), Coverage Analysis, Labor Cost Estimate, Compliance Notes, Fairness Notes, Evidence Gaps, Claims.

**Reviewer criteria** (score 0–10, weighted):
1. **Coverage** (30%) — all peak hours adequately staffed by role?
2. **Compliance** (25%) — flag violations under `COMPLIANCE FLAGS:`.
3. **Cost Efficiency** (20%) — overtime minimized? within budget?
4. **Fairness** (15%) — shifts equitable? availability honored?
5. **Actionability** (10%) — schedule specific enough to post?

**Convergence:** score ≥ 7.5 **and** zero `COMPLIANCE FLAGS`.

**Production gaps:** live HCM, automated labor-law lookup, shift-swap/time-off, payroll write-back, manager approval gate.

### Wave 1 skill templates (9)

| File | Purpose |
|---|---|
| `demand_signal.md` | Analyze historical sales + trend |
| `demand_seasonality_audit.md` | Challenge seasonality assumptions |
| `demand_stockout_risk.md` | Stockout vs. spoilage tradeoff |
| `demand_weather_impact.md` | Factor weather into demand adjustment |
| `demand_unemployment_rate.md` | Unemployment as spending signal |
| `labor_schedule_draft.md` | Draft weekly schedule |
| `labor_compliance_check.md` | Verify against labor law |
| `labor_coverage_audit.md` | Audit peak hour coverage |
| `labor_unemployment_rate.md` | Unemployment as staffing pool signal |

---

## Wave 2 — sweep convention recap

Every Wave-2 workflow (and existing Wave-1) MUST:

1. Define a `*Request` dataclass with `to_prompt_text()`.
2. Sanitize all request text via `sanitize_for_prompt`.
3. Loop up to `config.max_review_rounds`; convergence = `review.approved AND not current_flags`.
4. Register `## Claims` lines into `self.ledger` with `_register_claims`.
5. Add reviewer critique to `self.wiki.add_feedback`.
6. Extract flag list with `_extract_*_flags` parser; halt convergence on any flag.
7. Build a `_build_*_checklist` listing human-action items.
8. Return `WorkflowResult` with output suffixed by `_DISCLAIMER`, metadata including flag list, checklist, and `ledger_summary`.
9. PRODUCTION_GAPS docstring at the top.
10. Cite ARIS in the module docstring.

Skill templates are flat files under `src/adv_multi_agent/retail/skills/templates/`, prefixed with the scenario noun.

---

## Wave 2 — per-scenario specs

### 1. Food recall scope — `RecallScopeWorkflow`

**Gate type:** `SCOPE FLAGS` + **reviewer-veto**. Highest stakes; ARIS irreversible-decision pattern applied to retail safety. Differs from existing two: reviewer can issue a VETO that blocks convergence regardless of score.

**Request fields:**
- `contamination_signal: str` — pathogen / supplier alert / customer complaint summary
- `supplier_lot: str` — lot codes implicated
- `product_skus: str` — affected SKUs
- `distribution_window: str` — production + ship dates
- `stores_in_scope: str` — store IDs receiving the lot
- `consumer_exposure: str` — units sold to date; demographic exposure if known
- `regulatory_context: str` — FDA / USDA / state agency requirements
- `competing_evidence: str` — conflicting signals (lab results, supplier denials)

**Reviewer flags to detect:**
- `SCOPE FLAGS:` — recall too narrow (missed lots/stores/dates) OR too broad (unjustified expansion)
- `EVIDENCE FLAGS:` — recall scoped without primary evidence (lab confirm, regulatory directive, traceable lot match)
- `REVIEWER VETO:` — any condition requiring halt + escalate to human safety officer (e.g. life-safety signal without regulatory contact)

**Convergence:** `approved AND not scope_flags AND not evidence_flags AND not veto`. If `veto` is raised, workflow returns immediately with `converged=False`, `metadata["veto_reason"]` set.

**Veto control flow (spec):**
1. Each round: executor → output → register claims → reviewer → parse score + scope_flags + evidence_flags + veto in one pass over the critique.
2. `wiki.add_feedback` and `ledger.add` for that round run **before** the veto check. Veto is a halt, not a rollback — the audit trail must record what was vetoed and why.
3. On veto: return immediately with
   - `output` = round's draft + `_DISCLAIMER` + banner `⚠️  REVIEWER VETO — see metadata["veto_reason"]` (do NOT replace the draft; safety officer must see what was vetoed).
   - `rounds` = current `round_num`.
   - `final_score` = score parsed this round (may be high; veto is independent of score).
   - `converged` = `False`.
   - `metadata["veto_reason"]` = verbatim line(s) after `REVIEWER VETO:` (sanitized, capped at `config.max_wiki_body_chars`).
4. Veto check runs **after** flag extraction (flags also captured into metadata).
5. Tests cover: veto with high score (score=9, veto=True → not converged); veto with flags (both captured); no veto (normal convergence unchanged).

**Skill templates:** `recall_scope_audit.md`, `recall_lot_traceability.md`, `recall_consumer_exposure.md`, `recall_regulatory_check.md`, `recall_communications_draft.md`

**Checklist items** (always):
- Notify FDA/USDA per 21 CFR Part 7
- Pull affected lots from all stores in scope
- Draft consumer notification (press release + in-store signage)
- Stop downstream sale at warehouse + store level
- Sign off: safety officer + legal + comms
- Re-audit recall scope every 24h until closed

### 2. Loyalty/personalization offers — `LoyaltyOfferWorkflow`

**Gate type:** `FAIRNESS FLAGS`. Mirrors parole `BIAS FLAGS:` pattern.

**Request fields:**
- `customer_segment: str` — segment name + size + demographics summary
- `offer_proposal: str` — discount / bundle / threshold under consideration
- `historical_response: str` — past loyalty-program performance for similar offer
- `margin_floor: str` — minimum acceptable contribution margin
- `allowed_attributes: list[str]` — explicit allowlist of customer fields the segment may use (e.g. `["purchase_history", "loyalty_tier", "store_visits"]`)
- `disallowed_attributes: list[str]` — explicit denylist of fields and known proxies (e.g. `["zip_code", "language_preference", "first_name", "household_income_inferred"]`); reviewer treats any criterion derived from these as a `FAIRNESS FLAGS:` candidate
- `competing_offers: str` — concurrent promos or competitor offers
- `gaming_risk: str` — any structural exploit path

**Reviewer flags:**
- `FAIRNESS FLAGS:` — segment uses protected proxy (ZIP→race, language→ethnicity, etc.)
- `MARGIN FLAGS:` — projected contribution margin below floor without justification
- `GAMING FLAGS:` — exploit path material fraction of customers could take

**Convergence:** all three flag lists empty.

**Skill templates:** `loyalty_segment_audit.md`, `loyalty_fairness_check.md`, `loyalty_margin_check.md`, `loyalty_gaming_risk.md`

**Checklist:**
- Legal review of segment criteria for protected-class proxies
- Confirm margin floor with category manager
- Stress-test gaming path with finance + ops
- CMO approval before launch

### 3. Promo/markdown optimization — `PromoMarkdownWorkflow`

**Gate type:** `ELASTICITY FLAGS` + `MARGIN FLAGS`.

**Request fields:**
- `sku: str`
- `category: str`
- `current_price: str`
- `inventory_on_hand: str`
- `weeks_of_supply: str`
- `competitor_pricing: str`
- `elasticity_estimate: str` — historical / category benchmark
- `margin_floor: str` — minimum acceptable per-unit margin
- `promo_window: str` — planned start + end dates
- `cannibalization_risk: str` — other SKUs in basket absorbing demand

**Reviewer flags:**
- `ELASTICITY FLAGS:` — promo depth assumes elasticity not supported by inputs
- `MARGIN FLAGS:` — net margin (incl. cannibalization) below floor
- `TIMING FLAGS:` — overlap with competing campaign or major demand event without justification

**Convergence:** all three flag lists empty.

**Skill templates:** `promo_elasticity_audit.md`, `promo_margin_math.md`, `promo_cannibalization_check.md`, `promo_timing_check.md`

### 4. Supplier negotiation briefs — `SupplierBriefWorkflow`

**Gate type:** `BATNA FLAGS`.

**Request fields:**
- `supplier_name: str`
- `category: str`
- `current_terms: str` — price, payment, MOQ, lead time
- `target_terms: str` — what the buyer wants
- `volume_history: str` — last 12 months
- `alternatives: str` — backup suppliers (names + relative cost)
- `cost_drivers: str` — input cost trends supplier may cite
- `relationship_context: str` — strategic vs commodity supplier
- `negotiation_constraints: str` — corporate policies, ESG requirements

**Reviewer flags:**
- `BATNA FLAGS:` — "no alternative supplier" or alternative hand-waved
- `COST FLAGS:` — buyer asks below defensible cost floor
- `RELATIONSHIP FLAGS:` — proposed tactic damages strategic supplier without acknowledgement

**Convergence:** all three flag lists empty.

**Skill templates:** `supplier_batna_audit.md`, `supplier_cost_floor.md`, `supplier_relationship_check.md`, `supplier_brief_draft.md`

### 5. Inventory replenishment — `InventoryReplenishmentWorkflow`

**Gate type:** `LEAD-TIME FLAGS` + `STOCKOUT FLAGS`.

Note: **distinct from `DemandForecastWorkflow`** — demand produces a unit forecast; replenishment turns it into a per-DC / per-store order schedule across SKUs.

**Request fields:**
- `dc_id: str` — distribution center
- `sku_list: str` — SKUs in scope with current on-hand + on-order
- `demand_forecast: str` — accepts a `DemandForecastWorkflow` output or external forecast
- `lead_times: str` — per-supplier
- `safety_stock_policy: str` — corporate rule (e.g. 1.5σ)
- `dc_capacity: str` — physical / labor constraint
- `truck_economics: str` — full-truck vs LTL break-even
- `supplier_constraints: str` — MOQ, case pack, ship-day windows

**Reviewer flags:**
- `LEAD-TIME FLAGS:` — order qty ignores stated lead time or assumes future improvement
- `STOCKOUT FLAGS:` — projected on-hand drops below safety stock during planning window
- `CAPACITY FLAGS:` — order pattern exceeds DC capacity or supplier MOQ

**Convergence:** all three flag lists empty.

**Skill templates:** `replenishment_lead_time_audit.md`, `replenishment_stockout_check.md`, `replenishment_capacity_check.md`, `replenishment_truck_economics.md`

### 6. Private label product decisions — `PrivateLabelWorkflow`

**Gate type:** `CANNIBALIZATION FLAGS` + `BRAND FLAGS`.

**Request fields:**
- `proposed_sku: str` — name + category + positioning
- `target_price: str`
- `target_cost: str` — landed cost from co-manufacturer
- `national_brand_baseline: str` — incumbent SKU, share, price
- `category_margin: str` — current category margin mix
- `cannibalization_estimate: str` — % of demand shifting from national brand
- `brand_positioning: str` — fit with house brand identity
- `quality_assurance: str` — testing protocol, recall readiness
- `co_manufacturer: str` — vendor + audit status

**Reviewer flags:**
- `CANNIBALIZATION FLAGS:` — total category margin drops despite higher per-unit private-label margin
- `BRAND FLAGS:` — positioning conflicts with house brand identity, or QA gap
- `SUPPLY FLAGS:` — co-manufacturer audit stale or capacity unproven

**Convergence:** all three flag lists empty.

**Skill templates:** `private_label_cannibalization.md`, `private_label_brand_fit.md`, `private_label_qa_check.md`, `private_label_pricing.md`

---

## Cross-cutting decisions

**D-RETAIL-1: Reviewer-veto pattern (new).**
Only `RecallScopeWorkflow` uses it. Veto is a string the reviewer can emit under `REVIEWER VETO:`; presence ends the workflow immediately with `converged=False`. Documented in `decisions.md` before PR #1 of the sweep.

**D-RETAIL-2: No shared base class.**
Six workflows could share a "FlagGatedWorkflow" base. Rejected — premature abstraction (CLAUDE.md anti-pattern). After all six exist, if pattern is identical, extract base. *(Re-evaluated post-sweep: held — see D-RETAIL-7 in `decisions.md`.)*

**D-RETAIL-3: Skill template prefix.**
Per-scenario noun: `demand_*`, `labor_*`, `recall_*`, `loyalty_*`, `promo_*`, `supplier_*`, `replenishment_*`, `private_label_*`. Avoids collisions and is greppable.

**D-RETAIL-4: One example per scenario.**
`examples/retail/<scenario>.py` mirrors `demand_forecasting.py` + `labor_scheduling.py`.

**D-RETAIL-5: No live data integrations.**
Synthetic data only. PRODUCTION_GAPS docstring lists what production deployment would require.

**D-RETAIL-6: Tests.** Per workflow:
- Convergence on clean input
- Non-convergence when reviewer flags present
- Flag parser extracts under each flag header
- Claims registered into ledger
- Disclaimer present in output
- For recall: veto short-circuits with `metadata["veto_reason"]`

**Initial-wave decisions (pre-sweep):**
- Approach A (strict domain separation) — no shared retail base class, no abstraction beyond what parole already provides.
- Flat skill templates dir with prefixes — avoids nested `demand/` and `labor/` subdirs, parity with parole.
- Convergence gates mirror parole: score threshold + zero domain-specific flags.
- Synthetic data only — no live Kroger API integration.

---

## Per-PR convention additions (Wave 2)

Every Wave-2 scenario PR (in addition to the workflow + skills + example + tests) MUST touch:

- `docs/scenarios.md` — flip candidate → built
- `src/adv_multi_agent/retail/__init__.py` — export new `*Workflow` + `*Request`
- `CHANGELOG.md` — Unreleased entry naming workflow + flag types
- `docs/SECURITY_MODEL.md` — one-line entry per new prompt template (new injection surface)
- `pyproject.toml` — verify retail skills already in `package-data` (added Wave 1, must stay)

Decision-doc rule: **PR #1 of Wave 2 carries D-RETAIL-1..6 in `docs/decisions.md`** — all six are cross-cutting and apply to every later PR. Don't fragment.

Pre-PR gate (run on every branch before push):
```
python scripts/check_no_secrets.py
ruff check .
mypy src
pytest -q
```

## Convention-helper extraction checkpoint (after Wave-2 PR #2-3)

`_extract_*_flags`, `_register_claims`, `_build_*_checklist` will be copied across 6 workflows. Do NOT extract pre-emptively. After PR #2 lands, evaluate whether:
- `_extract_flags(critique, header: str) -> list[str]` belongs in `core/_internal.py`
- `_register_claims` belongs on `BaseWorkflow` (it already takes `self.ledger`)

If divergence appears (flag parsers genuinely differ), keep them inline. Decision deferred until evidence of duplication-without-divergence. *(Outcome: `_extract_flags` + `extract_veto_directive` hoisted into `core/_internal.py` post-sweep; M1 / M-PC-1 / H-IND-1 all closed via single regex changes there.)*

---

## Out-of-scope for this sweep

- ML baseline integration (PRODUCTION_GAPS row)
- Third-model auditor cascade (ARIS §3.1)
- Approval gate / append-only audit store
- Cross-workflow chaining (replenishment consuming demand forecast at runtime)

---

## Pre-sprint checklist (Wave 2)

- [x] Advisor sign-off on this design doc
- [x] Decision entries D-RETAIL-1..6 appended to `docs/decisions.md`
- [x] Branch-per-scenario plan agreed (6 PRs)
- [x] Existing retail surface scanned for convention drift (only 2 workflows at sweep start; low risk)
