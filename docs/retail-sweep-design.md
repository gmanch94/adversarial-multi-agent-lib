# Retail Sweep — Design Doc (six remaining scenarios)

Last updated: 2026-05-13
Status: **APPROVED — advisor 2026-05-13 (blockers folded in: package-data, veto control flow, per-PR additions)**

Build order (1 PR per scenario, sequential):

1. **Food recall scope** — `RecallScopeWorkflow` (operations + safety)
2. **Loyalty/personalization offers** — `LoyaltyOfferWorkflow` (customer)
3. **Promo/markdown optimization** — `PromoMarkdownWorkflow` (commercial)
4. **Supplier negotiation briefs** — `SupplierBriefWorkflow` (commercial)
5. **Inventory replenishment** — `InventoryReplenishmentWorkflow` (operations)
6. **Private label product decisions** — `PrivateLabelWorkflow` (commercial)

---

## Convention recap (from `demand_forecasting.py` + `labor_scheduling.py`)

Every retail workflow MUST:

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

Skill templates are flat files under `src/adv_multi_agent/retail/skills/templates/`, prefixed with the scenario noun (e.g. `recall_*`, `loyalty_*`).

---

## Per-scenario specs

### 1. Food recall scope — `RecallScopeWorkflow`

**Gate type:** `SCOPE FLAGS` + **reviewer-veto**. Highest stakes; this is the ARIS irreversible-decision pattern applied to retail safety. Differs from existing two: reviewer can issue a VETO that blocks convergence regardless of score.

**Request fields:**
- `contamination_signal: str` — pathogen / supplier alert / customer complaint summary
- `supplier_lot: str` — lot codes implicated
- `product_skus: str` — affected SKUs
- `distribution_window: str` — production + ship dates
- `stores_in_scope: str` — store IDs receiving the lot
- `consumer_exposure: str` — units sold to date; demographic exposure if known
- `regulatory_context: str` — FDA / USDA / state agency requirements
- `competing_evidence: str` — any conflicting signals (lab results, supplier denials)

**Reviewer flags to detect:**
- `SCOPE FLAGS:` — recall too narrow (missed lots, missed stores, missed dates) OR too broad (unjustified scope expansion)
- `EVIDENCE FLAGS:` — recall scoped without primary evidence (lab confirm, regulatory directive, traceable lot match)
- `REVIEWER VETO:` — any condition that requires the recall to halt and escalate to human safety officer (e.g. life-safety signal but no regulatory contact yet)

**Convergence:** `approved AND not scope_flags AND not evidence_flags AND not veto`. If `veto` is raised, workflow returns immediately with `converged=False`, `metadata["veto_reason"]` set.

**Veto control flow (spec):**
1. Each round: executor → output → register claims → reviewer → parse score + scope_flags + evidence_flags + veto in one pass over the critique.
2. `wiki.add_feedback` and `ledger.add` for that round run **before** the veto check. Veto is a halt, not a rollback — the audit trail must record what was vetoed and why.
3. On veto: return immediately with
   - `output` = the round's draft + `_DISCLAIMER` + a banner reading `⚠️  REVIEWER VETO — see metadata["veto_reason"]` (do NOT replace the draft; the safety officer must see what was vetoed).
   - `rounds` = current `round_num`.
   - `final_score` = score parsed from this round (may be high; veto is independent of score).
   - `converged` = `False`.
   - `metadata["veto_reason"]` = the verbatim line(s) after `REVIEWER VETO:` (sanitized, capped at `config.max_wiki_body_chars`).
4. Veto check runs **after** flag extraction (flags are also captured into metadata for completeness).
5. Tests must cover: veto with high score (score=9, veto=True → not converged); veto with flags (both captured); no veto (normal convergence path unchanged).

**Skill templates:** `recall_scope_audit.md`, `recall_lot_traceability.md`, `recall_consumer_exposure.md`, `recall_regulatory_check.md`, `recall_communications_draft.md`

**Checklist items** (always):
- Notify FDA/USDA per 21 CFR Part 7
- Pull affected lots from all stores in scope
- Draft consumer notification (press release + in-store signage)
- Stop downstream sale at warehouse + store level
- Sign off: safety officer + legal + comms
- Re-audit recall scope every 24h until closed

---

### 2. Loyalty/personalization offers — `LoyaltyOfferWorkflow`

**Gate type:** `FAIRNESS FLAGS`. Mirrors parole `BIAS FLAGS:` pattern.

**Request fields:**
- `customer_segment: str` — segment name + size + demographics summary
- `offer_proposal: str` — discount / bundle / threshold being considered
- `historical_response: str` — past loyalty-program performance for similar offer
- `margin_floor: str` — minimum acceptable contribution margin
- `protected_attributes: str` — fields the segment is allowed / not allowed to be derived from
- `competing_offers: str` — concurrent promos or competitor offers
- `gaming_risk: str` — any structural way customers could exploit the offer

**Reviewer flags to detect:**
- `FAIRNESS FLAGS:` — segment definition uses a protected proxy (ZIP→race, language preference→ethnicity, etc.)
- `MARGIN FLAGS:` — projected contribution margin below floor without justification
- `GAMING FLAGS:` — exploit path that material fraction of customers could take

**Convergence:** all three flag lists empty.

**Skill templates:** `loyalty_segment_audit.md`, `loyalty_fairness_check.md`, `loyalty_margin_check.md`, `loyalty_gaming_risk.md`

**Checklist:**
- Legal review of segment criteria for protected-class proxies
- Confirm margin floor with category manager
- Stress-test gaming path with finance + ops
- Approval from CMO before launch

---

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
- `cannibalization_risk: str` — other SKUs in basket that may absorb demand

**Reviewer flags:**
- `ELASTICITY FLAGS:` — promo depth assumes elasticity not supported by inputs
- `MARGIN FLAGS:` — net margin (incl. cannibalization) drops below floor
- `TIMING FLAGS:` — promo overlaps with a competing campaign or major demand event without justification

**Convergence:** all three flag lists empty.

**Skill templates:** `promo_elasticity_audit.md`, `promo_margin_math.md`, `promo_cannibalization_check.md`, `promo_timing_check.md`

---

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
- `BATNA FLAGS:` — "no alternative supplier identified" or alternative is hand-waved
- `COST FLAGS:` — buyer asks below a defensible cost floor
- `RELATIONSHIP FLAGS:` — proposed tactic damages strategic supplier without explicit acknowledgement

**Convergence:** all three flag lists empty.

**Skill templates:** `supplier_batna_audit.md`, `supplier_cost_floor.md`, `supplier_relationship_check.md`, `supplier_brief_draft.md`

---

### 5. Inventory replenishment — `InventoryReplenishmentWorkflow`

**Gate type:** `LEAD-TIME FLAGS` + `STOCKOUT FLAGS`.

Note: this is **distinct from `DemandForecastWorkflow`** — demand produces a unit forecast; replenishment turns the forecast into a per-DC / per-store order schedule across SKUs.

**Request fields:**
- `dc_id: str` — distribution center
- `sku_list: str` — list of SKUs in scope with current on-hand + on-order
- `demand_forecast: str` — accepts a `DemandForecastWorkflow` output or external forecast
- `lead_times: str` — per-supplier
- `safety_stock_policy: str` — corporate rule (e.g. 1.5σ)
- `dc_capacity: str` — physical / labor constraint
- `truck_economics: str` — full-truck vs LTL break-even
- `supplier_constraints: str` — MOQ, case pack, ship-day windows

**Reviewer flags:**
- `LEAD-TIME FLAGS:` — order quantity ignores stated lead time or assumes future improvement
- `STOCKOUT FLAGS:` — projected on-hand drops below safety stock during the planning window
- `CAPACITY FLAGS:` — order pattern exceeds DC capacity or supplier MOQ

**Convergence:** all three flag lists empty.

**Skill templates:** `replenishment_lead_time_audit.md`, `replenishment_stockout_check.md`, `replenishment_capacity_check.md`, `replenishment_truck_economics.md`

---

### 6. Private label product decisions — `PrivateLabelWorkflow`

**Gate type:** `CANNIBALIZATION FLAGS` + `BRAND FLAGS`.

**Request fields:**
- `proposed_sku: str` — name + category + positioning
- `target_price: str`
- `target_cost: str` — landed cost from co-manufacturer
- `national_brand_baseline: str` — incumbent SKU, share, price
- `category_margin: str` — current category margin mix
- `cannibalization_estimate: str` — % of demand expected to shift from national brand
- `brand_positioning: str` — how this fits the private-label house brand
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
Six workflows could share a "FlagGatedWorkflow" base. Rejected — premature abstraction (CLAUDE.md anti-pattern). After all six exist, if pattern is identical, extract base.

**D-RETAIL-3: Skill template prefix.**
Per-scenario noun: `recall_*`, `loyalty_*`, `promo_*`, `supplier_*`, `replenishment_*`, `private_label_*`. Avoids collisions and is easy to grep.

**D-RETAIL-4: One example per scenario.**
`examples/retail/<scenario>.py` mirrors existing `demand_forecasting.py` + `labor_scheduling.py`.

**D-RETAIL-5: No live data integrations.**
Synthetic data only. PRODUCTION_GAPS docstring lists what production deployment would require.

**D-RETAIL-6: Tests.**
Per workflow:
- Convergence on clean input
- Non-convergence when reviewer flags present
- Flag parser extracts under each flag header
- Claims registered into ledger
- Disclaimer present in output
- For recall: veto short-circuits with `metadata["veto_reason"]`

---

## Per-PR convention additions

Every scenario PR (in addition to the workflow + skills + example + tests) MUST touch:

- `docs/scenarios.md` — flip candidate → built
- `src/adv_multi_agent/retail/__init__.py` — export new `*Workflow` + `*Request`
- `CHANGELOG.md` — Unreleased entry naming workflow + flag types
- `docs/SECURITY_MODEL.md` — one-line entry per new prompt template (new injection surface)
- `pyproject.toml` — verify retail skills already in `package-data` (added in PR #1, must stay)

Decision-doc rule:
- **PR #1 carries D-RETAIL-1..6 in `docs/decisions.md`** — all six are cross-cutting and apply to every later PR. Don't fragment.

Pre-PR gate (run on every branch before push):
```
python scripts/check_no_secrets.py
ruff check .
mypy src
pytest -q
```

## Convention-helper extraction checkpoint (after PR #2-3)

`_extract_*_flags`, `_register_claims`, `_build_*_checklist` will be copied across 6 workflows. Do NOT extract pre-emptively. After PR #2 lands, evaluate whether:
- `_extract_flags(critique, header: str) -> list[str]` belongs in `core/_internal.py`
- `_register_claims` belongs on `BaseWorkflow` (it already takes `self.ledger`)

If divergence appears (flag parsers genuinely differ), keep them inline. Decision deferred until evidence of duplication-without-divergence.

---

## Out-of-scope for this sweep

- ML baseline integration (PRODUCTION_GAPS row)
- Third-model auditor cascade (ARIS §3.1)
- Approval gate / append-only audit store
- Cross-workflow chaining (replenishment consuming demand forecast at runtime)

---

## Pre-sprint checklist

- [ ] Advisor sign-off on this design doc
- [ ] Decision entries D-RETAIL-1..6 appended to `docs/decisions.md`
- [ ] Branch-per-scenario plan agreed (6 PRs)
- [ ] Existing retail surface scanned for convention drift (only 2 workflows; low risk)
