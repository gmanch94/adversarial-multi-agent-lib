---
marp: true
theme: adv-slides
paginate: true
---

<!-- _class: lead -->

# Retail Decision Support
## Adversarial Multi-Agent across 8 Retail Workflows

Technical · Design · Safety Reference

&nbsp;

*Domain application of the adv-multi-agent library*
*Product & Engineering Leadership · May 2026*

&nbsp;

*Based on ARIS (Yang, Li, Li — SJTU + Shanghai Innovation Institute, arXiv:2605.03042)*

---

<!-- _class: section -->

# 1. Problem Context

*Why adversarial multi-agent for retail decisions?*

---

## The Scale Problem

Retail decisions at store-day-SKU resolution repeat at scale:

| Decision | Frequency | Per-instance stake |
|---|---|---|
| Replenishment (per SKU × store × week) | ~40k SKUs × weekly | $10s–$100s spoilage / lost sales |
| Labor schedule (per store × week) | Weekly | $1k–$10k payroll + compliance risk |
| Promo / markdown | Weekly–monthly | $1k–$1M margin swing |
| Loyalty offer | Weekly | $10k–$10M fairness + margin risk |
| Supplier negotiation | Per renewal | $100k–$100M margin |
| Inventory replenishment (per DC) | Weekly | $10k–$1M working capital |
| Private-label launch | Per SKU | $100k–$100M category margin |
| Recall scope | Per incident | Lives + brand + regulatory |

A confident-but-wrong LLM at this scale silently compounds errors — spoilage, OT violations, segment-proxy fairness gaps, eroded supplier relationships, irreversible launches, under-scoped recalls.

> Human review of every recommendation does not scale. Auditing the *recommendation engine* does.

---

## The Cross-Model Solution

Two models from different families propose and challenge the same recommendation. Failures correlated within a model family are caught by the other:

```
retail.*Request   (8 workflow variants)
  │
  ▼
Executor (Claude Opus 4.7, adaptive thinking)
  │  produces evidence-grounded advisory brief
  ▼
Reviewer (GPT-4o — different family, multi-mandate)
  │  1. Quality audit                   (score 0–10)
  │  2. Domain audit                    (1–3 flag classes per workflow)
  │  3. Reviewer veto                   (recall only — irreversible-decision gate)
  ▼
score ≥ threshold AND zero domain flags AND no veto?
  YES → converged, return output
  NO  → executor revises (critique + flags injected)
         repeat until convergence or MAX_REVIEW_ROUNDS
```

**Convergence is a conjunction** — quality gate *and* every domain-flag class clear *and* no veto.

---

<!-- _class: section -->

# 2. Eight Workflows, One Pattern

*Same recipe, different domain audits*

---

## Pattern Parity

```
adv_multi_agent.retail.workflows/
├── demand_forecasting.py         DemandForecastWorkflow + ForecastRequest
├── labor_scheduling.py           LaborSchedulingWorkflow + SchedulingRequest
├── recall_scope.py               RecallScopeWorkflow + RecallRequest
├── loyalty_offer.py              LoyaltyOfferWorkflow + LoyaltyOfferRequest
├── promo_markdown.py             PromoMarkdownWorkflow + PromoRequest
├── supplier_brief.py             SupplierBriefWorkflow + SupplierBriefRequest
├── inventory_replenishment.py    InventoryReplenishmentWorkflow + InventoryReplenishmentRequest
└── private_label.py              PrivateLabelWorkflow + PrivateLabelRequest
```

Every workflow:
- Extends `BaseWorkflow` from `core/`; inherits `_register_claims(output, round_num)`
- Uses `extract_flags(critique, header)` from `core._internal` for sibling-header-safe parsing
- Sanitises every free-text field via `sanitize_for_prompt(..., max_chars=6000)`
- Appends a programmatic `_DISCLAIMER` advisory-only banner
- Carries a `PRODUCTION_GAPS` docstring naming exactly what production deployment would require
- Has 4–5 bundled skill templates and one synthetic-data example

---

## Workflow Inventory

| Workflow | Gate Type | Convergence requires zero flags in |
|---|---|---|
| `DemandForecastWorkflow` | Single | `ASSUMPTION FLAGS` |
| `LaborSchedulingWorkflow` | Single | `COMPLIANCE FLAGS` |
| `RecallScopeWorkflow` | Dual + veto | `SCOPE` + `EVIDENCE` + reviewer veto |
| `LoyaltyOfferWorkflow` | Triple | `FAIRNESS` + `MARGIN` + `GAMING` |
| `PromoMarkdownWorkflow` | Triple | `ELASTICITY` + `MARGIN` + `TIMING` |
| `SupplierBriefWorkflow` | Triple | `BATNA` + `COST` + `RELATIONSHIP` |
| `InventoryReplenishmentWorkflow` | Triple | `LEAD-TIME` + `STOCKOUT` + `CAPACITY` |
| `PrivateLabelWorkflow` | Triple | `CANNIBALIZATION` + `BRAND` + `SUPPLY` |

Five of eight workflows use the **triple-flag** gate pattern. Recall is the only workflow with a **reviewer-veto** channel for irreversible decisions.

---

## Workflow 1 — Demand Forecasting

**`ForecastRequest`** consumes a sales-history narrative, a category context, weather/event signals, and a buyer's working hypothesis.

**`ASSUMPTION FLAGS`** fire when the executor imports a seasonality / weather / event adjustment not grounded in the input data — the most common confident-but-wrong failure mode for LLM-assisted forecasting.

**Output:** 4-week unit forecast with each adjustment named, justified, and traced to an input field; replenishment recommendation (order qty + order-by + delivery + supplier); evidence-gap callout; buyer checklist.

---

## Workflow 2 — Labor Scheduling

**`SchedulingRequest`** consumes roster + availability + labor-law rules + traffic pattern + budget.

**`COMPLIANCE FLAGS`** fire when any shift violates a stated rule — OT, breaks, minor-labor, predictive-scheduling, availability. The revision prompt tells the executor explicitly: *fix the violation, do not merely note it.*

**Output:** day-by-day schedule with named assignments; coverage analysis by role; labor cost vs budget; per-rule pass/fail; fairness notes (hour distribution + availability honored); manager checklist.

---

## Workflow 3 — Food-Recall Scope

**`RecallRequest`** consumes contamination signal, supplier lot, affected SKUs, distribution window, stores in scope, consumer exposure, regulatory context, and competing evidence.

Three gates, all must clear:
- **`SCOPE FLAGS`** — recall too narrow (missed lots/stores/dates) OR too broad (unjustified expansion)
- **`EVIDENCE FLAGS`** — recall scoped without primary evidence (lab confirm, regulatory directive, traceable lot match)
- **`REVIEWER VETO:`** — reviewer halts the loop on a life-safety condition (e.g. signal but no regulatory contact). Audit-trail writes happen *before* the veto break.

**Output:** recall scope (lots, stores, dates); consumer-exposure assessment; regulatory-notification draft per 21 CFR Part 7; safety-officer checklist. On veto: draft + banner + `metadata["veto_reason"]` for safety-officer review.

---

## Workflow 4 — Loyalty / Personalization Offer

**`LoyaltyOfferRequest`** consumes segment definition, offer proposal, historical response, margin floor, explicit `allowed_attributes` and `disallowed_attributes` lists, competing offers, and known gaming risk.

Triple gate:
- **`FAIRNESS FLAGS`** — segment criteria derived from a disallowed attribute or known proxy (ZIP→race, language preference→ethnicity)
- **`MARGIN FLAGS`** — projected contribution margin below floor including cannibalization
- **`GAMING FLAGS`** — exploit path with no mitigation

`allowed_attributes` / `disallowed_attributes` are `list[str]` capped at 64 entries × 200 chars and routed through per-element `sanitize_for_prompt`.

**Output:** segment definition, offer mechanic, margin math, gaming-path mitigations, success metric + kill criteria, CMO checklist.

---

## Workflow 5 — Promo / Markdown Optimization

**`PromoRequest`** consumes SKU, category, current price, inventory, weeks-of-supply, competitor pricing, elasticity estimate with source, margin floor, promo window, and cannibalization risk.

Triple gate:
- **`ELASTICITY FLAGS`** — promo depth assumes elasticity not supported by the input (or extrapolates beyond the source's range)
- **`MARGIN FLAGS`** — adverse-case net margin below floor including cannibalization
- **`TIMING FLAGS`** — window collides with a concurrent campaign or major demand event without mitigation

**Output:** elasticity assumption with source, promo mechanic, central + adverse-case margin math, timing-risk mitigations, success metric + kill criteria, category-manager + finance checklist.

---

## Workflow 6 — Supplier Negotiation Brief

**`SupplierBriefRequest`** consumes supplier, category, current terms, target terms, volume history, alternatives, cost drivers, relationship context, and negotiation constraints.

Triple gate:
- **`BATNA FLAGS`** — no defensible alternative supplier identified, or alternatives hand-waved
- **`COST FLAGS`** — buyer ask below defensible cost floor implied by `cost_drivers`
- **`RELATIONSHIP FLAGS`** — proposed tactic damages a strategic supplier without explicit acknowledgement

**Output:** BATNA assessment; cost-floor defence anchored in input-cost drivers; opening / landing / walk-away terms; concession order with paired asks; talking points keyed to anticipated supplier objections; buyer + finance + legal checklist.

---

## Workflow 7 — Inventory Replenishment

**`InventoryReplenishmentRequest`** consumes DC ID, SKU list (on-hand + on-order), demand forecast, lead times (quoted + p90), safety-stock policy, DC capacity, truck economics, and supplier constraints.

Distinct from `DemandForecastWorkflow`: turns a unit forecast into a per-DC per-SKU PO schedule across SKUs.

Triple gate:
- **`LEAD-TIME FLAGS`** — order ignores stated lead time or assumes future improvement
- **`STOCKOUT FLAGS`** — projected on-hand drops below safety stock in planning window
- **`CAPACITY FLAGS`** — order pattern exceeds DC capacity or supplier MOQ / case-pack / ship-day

**Output:** per-SKU PO schedule, stockout projection (central + adverse), capacity check, truck economics, supply-planning + DC ops + sourcing checklist.

---

## Workflow 8 — Private-Label Decision

**`PrivateLabelRequest`** consumes proposed SKU, target price, target cost, national-brand baseline, category margin, cannibalization estimate, brand positioning, QA protocol, and co-manufacturer audit + capacity.

Triple gate:
- **`CANNIBALIZATION FLAGS`** — total category margin drops despite higher per-unit private-label margin
- **`BRAND FLAGS`** — positioning conflicts with house-brand identity or QA gap
- **`SUPPLY FLAGS`** — co-manufacturer audit stale or capacity unproven

**Output:** total-category-margin math (central + adverse), brand-fit assessment, supply-readiness verification, pricing stack, launch plan, category-management + brand + QA + sourcing checklist.

---

<!-- _class: section -->

# 3. Input Structure

*Free-text, structured fields, defensive caps*

---

## *Request Dataclass Pattern

Every workflow defines a per-workflow `*Request` dataclass:

```python
@dataclass
class PromoRequest:
    sku: str
    category: str
    current_price: str
    inventory_on_hand: str
    weeks_of_supply: str
    competitor_pricing: str
    elasticity_estimate: str       # explicit source required
    margin_floor: str
    promo_window: str
    cannibalization_risk: str

    def to_prompt_text(self) -> str: ...
```

**Free-text by design.** Caller integrates with POS, ERP, pricing-science feeds, etc. and provides a synthesis. The workflow reasons over the narrative; it does not parse structured time series.

---

## Defence-in-Depth on Inputs

| Layer | Mechanism |
|---|---|
| Per-field free-text cap | `sanitize_for_prompt(..., max_chars=6000)` on `request.to_prompt_text()` |
| List-of-string fields | Capped at 64 entries × 200 chars each (loyalty `allowed_attributes` / `disallowed_attributes`) |
| Revision-prompt context cap | `previous` output capped at 10k chars; critique at 4k; per-suggestion at 500 chars |
| Veto-text containment (recall) | `REVIEWER VETO:` directive stripped of control chars, capped at `Config.max_wiki_body_chars`, stored in metadata only — never replayed into a later prompt |
| Wiki context cap | `wiki.context_for_round` enforces total-char budget with fences |
| Claim text cap | `ClaimLedger` raises `ValueError` past `Config.max_claim_text_chars` |

Caller-supplied free-text is the primary injection surface; every boundary has a cap.

---

<!-- _class: section -->

# 4. The Three Gate Patterns

*Single-flag, triple-flag, reviewer-veto*

---

## Pattern A — Single-Flag Gate (demand, labor)

```
score ≥ threshold AND zero ASSUMPTION FLAGS    # demand
score ≥ threshold AND zero COMPLIANCE FLAGS    # labor
```

Used by the two pre-sweep workflows. The flag class is a single domain audit folded into the same reviewer that scores quality.

**When it's enough:** one domain failure mode dominates the risk; quality + that one audit clear the bar.

---

## Pattern B — Triple-Flag Gate (loyalty, promo, supplier, inventory, private-label)

```
score ≥ threshold
  AND zero FLAGS-class-1
  AND zero FLAGS-class-2
  AND zero FLAGS-class-3
```

Used by five workflows. Independent flag classes capture distinct failure modes:
- **Loyalty:** fairness × margin × gaming
- **Promo:** elasticity × margin × timing
- **Supplier:** BATNA × cost × relationship
- **Inventory:** lead-time × stockout × capacity
- **Private-label:** cannibalization × brand × supply

**Convergence is the conjunction.** A high-scoring brief with one flag class unresolved does not converge — the executor must remove or ground every flagged item.

---

## Pattern C — Reviewer Veto (recall only)

```
After flag extraction:
  audit-trail writes (wiki.add_feedback, claim ledger) happen FIRST
  if REVIEWER VETO: present → halt loop, converged=False
  else if approved AND zero flags → converged=True
  else → revise
```

Used by `RecallScopeWorkflow`. The veto channel lets the reviewer halt regardless of score on a life-safety condition.

**Why audit-trail-before-veto:** the safety officer must see what was vetoed and why. A rollback would lose the draft. The output keeps the draft + banner + `metadata["veto_reason"]`; the loop exits with `converged=False`.

**Tests cover:** veto with high score (score 9 + veto → not converged); veto with flags (both captured); no veto (normal path unchanged).

---

## Shared Helpers (D-RETAIL-2 checkpoint)

After three triple-flag workflows shipped, helpers were lifted into shared modules:

```python
# core/_internal.py
def extract_flags(critique: str, header: str) -> list[str]:
    """Sibling-header-safe parser. Stops at Overall / Key issues /
    inline UPPERCASE header / markdown #. Recognises None / None
    detected / n/a as empty markers."""

# core/workflow.py — BaseWorkflow
def _register_claims(self, output: str, round_num: int) -> None:
    """Parses ## Claims section, dedupes, registers into self.ledger."""
```

**No shared base class.** D-RETAIL-2 keeps each workflow's banner text, metadata keys, and checklist items inline — divergence per scenario is large enough that a base class would require config-dict injection that costs more than it saves.

---

<!-- _class: section -->

# 5. Skill Templates

*25 bundled retail skills*

---

## Skill Inventory

```
src/adv_multi_agent/retail/skills/templates/
├── demand_*               (5)  signal, seasonality, weather, unemployment, stockout-risk
├── labor_*                (4)  coverage, compliance, draft, unemployment
├── recall_*               (5)  scope, lot-traceability, consumer-exposure,
│                               regulatory, communications-draft
├── loyalty_*              (4)  segment-audit, fairness, margin, gaming
├── promo_*                (4)  elasticity, margin-math, cannibalization, timing
├── supplier_*             (4)  batna, cost-floor, relationship, brief-draft
├── replenishment_*        (4)  lead-time, stockout, capacity, truck-economics
└── private_label_*        (4)  cannibalization, brand-fit, qa-check, pricing
```

**25 retail skill templates total**, prefixed with the scenario noun (D-RETAIL-3).

**Bundled inside the wheel** — `SkillRegistry.bundled_skills_path(domain='retail')` works for pip-installed users. (Latent regression caught in PR #13: retail templates were missing from `package-data`; fixed.)

---

## Skill Template Anatomy

```markdown
---
name: promo_elasticity_audit
description: Audit a proposed elasticity assumption against the
  supplied evidence; flag any default-elasticity import not
  present in inputs
inputs: [sku, category, current_price, elasticity_estimate]
---
You are a pricing analyst auditing an elasticity claim ...

1. **Source check** — ...
2. **Range check** — ...
3. **Extrapolation check** — ...
4. **Category-fit check** — ...

Output format:
- Source verdict: [Primary / Borrowed / Unsupported]
- ELASTICITY FLAGS to surface to reviewer: [bullet list, or "None"]
- Required validation before launch: [...]
```

Each skill is a named reasoning pattern with input slots, structured analysis steps, and a structured output format that maps to a flag class.

---

## MCP Server Integration

```bash
# Register retail skill catalog with Claude Code
claude mcp add adv-multi-agent-skills -- \
  python -m adv_multi_agent.core.skills.mcp_server

# Same binary supports research, parole, retail via SKILLS_DOMAIN env
SKILLS_DOMAIN=retail python -m adv_multi_agent.core.skills.mcp_server
```

**4 MCP tools** exposed: `list_skills`, `describe_skills`, `get_skill`, `render_skill`. stdio transport.

**Same registry, same loader, same MCP server** for all three domains. New domains add `.md` files; no code changes.

---

<!-- _class: section -->

# 6. Output Surface

*What the decision-maker receives*

---

## Approver Checklist Pattern (every workflow)

Every workflow returns `metadata["approver_checklist"]` — a list of human-action items the decision-maker must complete before acting:

```
[ ] ⚠️  CANNIBALIZATION FLAGS DETECTED (2) — category management
    must re-validate total-category-margin against the household-
    basket substitution model before any launch commitment
[ ] Category-management review of cannibalization math for SKU-PL-COFFEE-12oz
[ ] Brand leadership sign-off: positioning coheres with house-brand identity
[ ] QA sign-off: testing protocol + recall readiness + regulatory compliance
[ ] Sourcing sign-off: co-manufacturer audit current AND capacity proven
[ ] No co-manufacturer commitment or shelf-set update without human review
```

Per-flag-class callouts appear conditionally (only when that flag class has accumulated entries). Baseline review items always appear.

---

## Metadata Surface

| Key | Type | Source |
|---|---|---|
| `<workflow-specific id>` (e.g. `sku`, `supplier_name`, `dc_id`, `proposed_sku`) | `str` | Request field — for caller correlation |
| `<flag_class>_flags` (e.g. `elasticity_flags`, `batna_flags`, `cannibalization_flags`) | `list[str]` | Accumulated across rounds, deduplicated |
| `approver_checklist` | `list[str]` | Built per-workflow including conditional flag callouts |
| `disclaimer` | `str` | The injected advisory-only banner text |
| `ledger_summary` | `dict` | `ClaimLedger.summary()` — `total` + per-status counts |
| `veto_reason` (recall only) | `str` | Verbatim reviewer-veto directive, sanitised + capped |
| `vetoed` (recall only) | `bool` | True only when reviewer veto triggered |

---

## Programmatic Disclaimer

Every workflow appends `_DISCLAIMER` to `output` in code, not in a prompt template:

```python
return WorkflowResult(
    output=f"{output}\n\n---\n\n{_DISCLAIMER}",
    ...
)
```

The disclaimer text varies by domain (recall mentions safety officer + 21 CFR Part 7; loyalty mentions CMO + fairness; supplier mentions buyer + finance + legal; etc.) but the **injection mechanism is identical** — the model cannot omit, edit, or suppress it via prompt content.

The same pattern is used for the recall veto banner: `⚠️  REVIEWER VETO — see metadata["veto_reason"]` is injected on the veto code path, never rendered by the model.

---

<!-- _class: section -->

# 7. Design Properties

*What carries over from core/*

---

## Inherited Safety Properties

All eight retail workflows extend `BaseWorkflow`. Every security property from `core/` carries over unchanged:

| Property | Mechanism |
|---|---|
| API keys redacted from `repr` / logs | `Config.__repr__`, `safe_dict()` |
| Path traversal blocked | `safe_resolve_path` asserts every persistence path under `workspace_dir` |
| Atomic writes | `atomic_write_text` (mkstemp + fsync + replace) |
| Score-injection blocked | `parse_first_json_or` (raw_decode from first `{`/`[`); `coerce_score` clamps to `[0, 10]` |
| Self-improvement auto-adoption blocked | Caller must call `wiki.approve_improvement(id, human_reviewer_id=...)` explicitly (M1 API break) |
| Wiki replay injection blocked | `context_for_round` excludes IMPROVEMENT kind, wraps entries in fences, sanitises, enforces budget |
| Claim text unbounded | `ClaimLedger._bound()` raises past `Config.max_claim_text_chars`; deduplicates |
| Long-running API calls | All clients constructed with `timeout=Config.request_timeout_seconds` |

---

## Domain-Specific Properties

| Property | Where |
|---|---|
| `*Request.to_prompt_text()` sanitised at boundary | Every retail workflow, `sanitize_for_prompt(..., max_chars=6000)` |
| `list[str]` fields capped | `LoyaltyOfferRequest.allowed_attributes` / `disallowed_attributes` — 64 × 200 |
| Reviewer-veto containment | `RecallScopeWorkflow._extract_veto` strips control chars, caps at `max_wiki_body_chars`, metadata-only |
| Triple-flag dict tracking | `current` / `accumulated` dicts keyed by flag header — no flag-class collision |
| Audit-trail-before-veto | `wiki.add_feedback` + `_register_claims` run BEFORE veto check (recall) |
| Conditional checklist callouts | Per-flag-class callouts only when that flag class has entries; baseline items always present |

---

<!-- _class: section -->

# 8. PRODUCTION_GAPS

*What this is not, by design*

---

## Gaps by Class (rolled up across 8 workflows)

| Gap class | Affects | What's needed |
|---|---|---|
| Live data feeds | All 8 | POS / HCM / WMS / ERP / supplier portals; weather / unemployment / commodity / freight / FX indices |
| Structured forecast | Demand, inventory | Prophet / LightGBM baseline; LLM adjusts the residual, not the baseline |
| Jurisdictional rule library | Labor, recall | Per-jurisdiction labor law (OT, breaks, minor-labor, predictive-scheduling), recall protocols (21 CFR Part 7, USDA, state) |
| Cost-driver feed | Supplier | Commodity indices, freight benchmarks, FX where relevant |
| Alternative-supplier registry | Supplier | Vetted backup-supplier registry with capacity, audit status, quoted unit cost |
| Co-manufacturer audit registry | Private-label | Last-audit-date + capacity + recall-readiness per vendor |
| Household-basket model | Loyalty, promo, private-label | Substitution matrix per SKU-pair — replaces narrated cannibalization rates |
| Brand-equity instrument | Private-label | Consumer panel or syndicated brand-equity feed for positioning fit |
| Third-model auditor cascade | All 8 (ARIS §3.1) | Separately configured auditor per high-stakes flag class |
| Human approval gate in code | All 8 | Orders / schedules / POs / proposals / launches must NOT auto-publish |

---

<!-- _class: section -->

# 9. Status & Adoption

*Where this is in the lifecycle*

---

## Status

| Property | Status |
|---|---|
| 8 retail workflows | ✅ Complete (demand, labor, recall, loyalty, promo, supplier, inventory, private-label) |
| 25 retail skill templates (5 + 4 + 5 + 4 + 4 + 4 + 4 + 4) | ✅ Complete |
| Single-flag, triple-flag, and reviewer-veto patterns | ✅ Complete |
| Shared helpers (`extract_flags`, `_register_claims`) | ✅ Complete (D-RETAIL-2 checkpoint, PR #16) |
| 8 retail examples (`examples/retail/*.py`) | ✅ Complete |
| 300 unit + integration tests | ✅ All passing |
| Design doc + locked decisions (D-RETAIL-1..6) | ✅ Complete |
| Live data integration adapters | ❌ PRODUCTION_GAP |
| Actuarial baselines (forecast, cannibalization, elasticity) | ❌ PRODUCTION_GAP |
| Jurisdictional rule library | ❌ PRODUCTION_GAP |
| Third-model auditor cascade (ARIS §3.1) | ❌ PRODUCTION_GAP |
| Human approval gate enforced in code | ❌ PRODUCTION_GAP |
| Append-only audit store | ❌ PRODUCTION_GAP |

---

## Who It Is For

**Retail data, operations, commercial, and safety teams** evaluating LLM augmentation across the decision surface. Each workflow's `PRODUCTION_GAPS` checklist names exactly what integration work is required before a pilot.

**Engineering teams** adding a new domain. Retail is the second reference implementation after parole; together they show the recipe for any high-stakes, data-rich domain. With the helper-extraction checkpoint in tree, the recipe is even cleaner for the third domain.

**Researchers** studying cross-model adversarial pairs in operational decisions where ground truth is observable post-hoc (forecast accuracy, compliance violations, post-promo lift, recall completeness, supplier-negotiation outcome, launch-period total-category-margin delta).

---

## Next Actions

| Action | Owner | Notes |
|---|---|---|
| Integration adapters (POS / HCM / WMS / ERP / supplier portals) | Engineering | Replace free-text inputs with live feeds |
| Actuarial baselines + cannibalization model | Data Science | LLM provides residual adjustments, not the baseline |
| Jurisdictional rule library | Legal + Engineering | Per-jurisdiction labor + ESG + compliance + recall rules |
| Co-manufacturer + supplier audit registry | Sourcing + QA + Engineering | Structured last-audit + capacity + recall-readiness per vendor |
| External signal feeds | Engineering | Weather, unemployment, commodity / freight / FX indices |
| Human approval gate in code | Engineering | Block auto-publish on orders / schedules / POs / launches |
| Pilot studies | Operations + Commercial | Single category, single DC, single store — 4-week shadow run per workflow before production |

---

<!-- _class: section -->

# References

---

## Citation

If you use this work, please cite the underlying research:

> Yang, R., Li, Y., & Li, S. (2026). *ARIS: Autonomous Research via Adversarial Multi-Agent Collaboration*. arXiv:2605.03042. Shanghai Jiao Tong University · Shanghai Innovation Institute.

The eight retail workflows are domain adaptations of the ARIS executor + cross-family-reviewer loop. Veto, triple-flag-gate, and helper-extraction patterns are project-specific extensions over the ARIS baseline; see `docs/decisions.md` D-RETAIL-1..6.

**Design doc:** `docs/superpowers/specs/2026-05-13-retail-domain-design.md` (APPROVED — advisor 2026-05-13)
**Decisions:** `docs/decisions.md`
**Examples:** `examples/retail/{demand_forecasting,labor_scheduling,recall_scope,loyalty_offer,promo_markdown,supplier_brief,inventory_replenishment,private_label}.py`

---

<!-- _class: lead -->

# Thank you

&nbsp;

**Install:** `pip install adv-multi-agent`

**MCP server (retail skills):** `SKILLS_DOMAIN=retail claude mcp add adv-multi-agent-skills -- python -m adv_multi_agent.core.skills.mcp_server`

&nbsp;

*All workflows are advisory-only. A qualified human retains full decision-making authority over every output.*
