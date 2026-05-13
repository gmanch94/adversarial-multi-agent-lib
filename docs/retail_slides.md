---
marp: true
theme: adv-slides
paginate: true
---

<!-- _class: lead -->

# Retail Decision Support
## Adversarial Multi-Agent for Demand & Labor

Technical · Design · Safety Reference

&nbsp;

*Domain application of the adv-multi-agent library*
*Product & Engineering Leadership · May 2026*

---

<!-- _class: section -->

# 1. Problem Context

*Why adversarial multi-agent for retail operations?*

---

## The Scale Problem

Retail operations decisions repeat at scale:

| Decision | Frequency | Per-instance stake |
|---|---|---|
| Replenishment (per SKU × store × week) | ~40k SKUs × weekly | $10s–$100s spoilage / lost sales |
| Labor schedule (per store × week) | Weekly | $1k–$10k payroll + compliance risk |
| Promo / markdown | Weekly–monthly | $1k–$1M margin swing |

A confident-but-wrong LLM at this scale silently compounds errors — spoilage in fresh, stockouts in dry, OT violations in labor, peak coverage gaps in service.

> Human review of every recommendation does not scale. Auditing the *recommendation engine* does.

---

## The Cross-Model Solution

Two models from different families propose and challenge the same recommendation. Failures correlated within a model family are caught by the other:

```
ForecastRequest / SchedulingRequest
  │
  ▼
Executor (Claude Opus 4.7, adaptive thinking)
  │  produces evidence-grounded advisory brief
  ▼
Reviewer (GPT-4o — different family, dual mandate)
  │  1. Quality audit             (score 0–10)
  │  2. Domain audit              (ASSUMPTION FLAGS / COMPLIANCE FLAGS)
  ▼
score ≥ threshold AND zero domain flags?
  YES → converged, return output
  NO  → executor revises (critique + flags injected)
         repeat until convergence or MAX_REVIEW_ROUNDS
```

**Convergence criterion is dual:** quality gate *and* domain-specific gate — both must clear.

---

<!-- _class: section -->

# 2. Two Workflows, One Pattern

*Same recipe, different domain audit*

---

## Pattern Parity

Both retail workflows extend `BaseWorkflow` and mirror the parole pattern:

| Aspect | DemandForecastWorkflow | LaborSchedulingWorkflow |
|---|---|---|
| Input dataclass | `ForecastRequest` (10 fields) | `SchedulingRequest` (8 fields) |
| Quality reviewer | Forecast grounding, risk balance, completeness, actionability | Coverage, cost efficiency, fairness, actionability |
| Domain audit gate | `ASSUMPTION FLAGS` | `COMPLIANCE FLAGS` |
| Failure mode caught | Confident but ungrounded seasonality / event adjustments | Labor-law violations hidden under good cost numbers |
| Human checklist | Buyer checklist | Manager checklist |
| Disclaimer (code-injected) | Not a purchase order | Not a published schedule |

The pattern is identical. The audit gate is the domain-specific variable.

---

## Workflow 1: Demand Forecasting

```
ForecastRequest
  │  store_id, sku, product_category,
  │  historical_sales (8 wk), current_inventory,
  │  lead_time_days, upcoming_events,
  │  seasonality_notes, weather_forecast,
  │  unemployment_rate
  ▼
Executor: structured forecast brief
  │  • Demand Signal Analysis
  │  • 4-week unit Forecast (each adjustment justified)
  │  • Replenishment Recommendation (qty + date + supplier)
  │  • Key Assumptions, Evidence Gaps, Claims
  ▼
Reviewer: quality + ASSUMPTION FLAGS
  │  Any seasonality / event / weather adjustment not
  │  grounded in input data is flagged.
  ▼
Converge → output + buyer checklist + disclaimer
```

---

## Workflow 2: Labor Scheduling

```
SchedulingRequest
  │  store_id, week_start, projected_traffic,
  │  staff_roster, labor_budget, local_events,
  │  state_labor_law_notes, unemployment_rate
  ▼
Executor: structured schedule
  │  • Day-by-day Schedule (named, role, start, end)
  │  • Coverage Analysis (per peak window)
  │  • Labor Cost Estimate (vs. budget)
  │  • Compliance Notes, Fairness Notes
  │  • Evidence Gaps, Claims
  ▼
Reviewer: quality + COMPLIANCE FLAGS
  │  Every shift checked against stated labor-law rules:
  │  OT threshold, break requirements, availability constraints.
  ▼
Converge → output + manager checklist + disclaimer
```

---

<!-- _class: section -->

# 3. Input Structure

*Free-text, structured fields*

---

## ForecastRequest

```python
@dataclass
class ForecastRequest:
    store_id:           str   # e.g. "KRO-OH-0042"
    sku:                str
    product_category:   str   # dairy, produce, beverages, ...
    historical_sales:   str   # "Wk1:320 Wk2:310 ... Wk8:330"
    current_inventory:  str   # on-hand + in-transit
    lead_time_days:     str
    upcoming_events:    str   # local events, holidays, promos
    seasonality_notes:  str   # known patterns
    weather_forecast:   str   # 2-week outlook
    unemployment_rate:  str   # local rate + trend
```

**Free-text by design.** Caller integrates with POS, ERP, weather API, etc. and provides a synthesis. The workflow does not parse structured time-series — it reasons over the narrative.

---

## SchedulingRequest

```python
@dataclass
class SchedulingRequest:
    store_id:                 str
    week_start:               str   # ISO date (Monday)
    projected_traffic:        str   # per-day + peak windows
    staff_roster:             str   # names, roles, FT/PT, availability
    labor_budget:             str   # weekly $ budget
    local_events:             str   # foot-traffic shocks
    state_labor_law_notes:    str   # OT, break, minor-labor rules
    unemployment_rate:        str   # labor pool + wage pressure
```

**Caller responsibility:** translate HCM, traffic counter, and labor-law sources into the per-field narrative. The workflow consumes the narrative and reasons over constraints.

---

## Input Quality Example

| Raw operational data | Workflow input (good narrative) |
|---|---|
| 8 rows of POS time-series | `"Wk1:320 Wk2:310 Wk3:335 Wk4:340 Wk5:315 Wk6:328 Wk7:342 Wk8:330"` |
| 5 employee records + availability matrix | `"Alice Chen — cashier, FT, available all 7 days; Bob Torres — cashier, PT, unavailable Fri; ..."` |
| State labor-law lookup table | `"Ohio: OT 1.5x >40h; 30-min break for shifts >6h; no minor restrictions (all staff 18+)"` |
| NWS API response | `"Warm and dry next 14 days; highs 78–84°F; no precipitation forecast."` |

> Free-text inputs make the workflow easy to wire up — and easy to misuse. Input quality is item #1 in the production-readiness checklist.

---

<!-- _class: section -->

# 4. The Two Audit Gates

*What makes adversarial in retail*

---

## ASSUMPTION FLAGS (Demand)

The executor must ground every forecast adjustment in input data. The reviewer flags any unsupported adjustment:

| Adjustment | Grounded? | Flag? |
|---|---|---|
| "Memorial Day lifts dairy ~15% based on historical holiday patterns" | Generic claim, not in `seasonality_notes` | ⚠️ FLAG |
| "Memorial Day lifts dairy ~8% per seasonality_notes which state 6–10% May–Aug" | Cites input field | ✓ Pass |
| "Promo reduces unit volume ~5%" | No explicit promo elasticity in input | ⚠️ FLAG |
| "Weather has negligible impact — dairy demand is weather-insensitive" | Generic; not justified from input | ⚠️ FLAG |
| "Weather warm and dry per weather_forecast; dairy demand is in-line with baseline" | Cites input field | ✓ Pass |

**Convergence requires zero flags.** Executor must either remove the adjustment or replace it with input-grounded evidence.

---

## COMPLIANCE FLAGS (Labor)

The executor must satisfy every stated labor-law rule. The reviewer flags any violation:

| Schedule line | State law (stated) | Flag? |
|---|---|---|
| `Alice 9-6 (cash)` (9 hrs) | "30-min break for shifts >6h" | ⚠️ FLAG (no break noted) |
| `Alice 9-6 with 30-min break 1-1:30` | Same rule | ✓ Pass |
| `Bob 11-7 Fri (cash)` | Roster: "Bob unavailable Friday" | ⚠️ FLAG |
| `Alice total: 42h` | "OT 1.5x >40h" — over threshold | ⚠️ FLAG |
| `Alice total: 40h` exact | Same rule | ✓ Pass |

**Convergence requires zero flags.** The revision prompt explicitly tells the executor: *fix the violation, do not merely note it.*

---

## Why "Fix, Not Note"

A common LLM failure mode: when challenged, the model adds a caveat instead of changing the recommendation:

| Reviewer flag | Bad executor revision | Good executor revision |
|---|---|---|
| "Bob scheduled on stated unavailable day" | "Note: Bob is unavailable Fri — manager should verify" | Remove Bob from Fri; add Alice or Eve |
| "Alice scheduled 42h (exceeds 40h OT threshold)" | "Note: Alice schedule includes 2h overtime" | Reduce Alice to 40h; redistribute 2h to PT staff |
| "Seasonality lift unsubstantiated" | "Note: seasonality factor is an estimate" | Remove the lift; reforecast at baseline |

The revision prompts are written to force action, not commentary. Tests verify both the revision behavior and the flag-extraction logic.

---

<!-- _class: section -->

# 5. Skill Templates

*The catalogue of named reasoning patterns*

---

## 9 Bundled Retail Skills

```
src/adv_multi_agent/retail/skills/templates/

  Demand (5):
    demand_signal.md             — baseline + trend + variance
    demand_seasonality_audit.md  — challenge seasonality assumptions
    demand_stockout_risk.md      — stockout vs. overstock tradeoff
    demand_weather_impact.md     — weather-driven demand adjustment
    demand_unemployment_rate.md  — consumer spending signal

  Labor (4):
    labor_schedule_draft.md      — draft schedule from roster + traffic
    labor_compliance_check.md    — verify against stated labor law
    labor_coverage_audit.md      — peak-hour coverage audit
    labor_unemployment_rate.md   — staffing pool + wage pressure
```

Loadable via the same MCP server as research/parole. Each is a `.md` with YAML frontmatter, validated by `SkillRegistry`.

---

## Skill Template Anatomy

```markdown
---
name: demand_signal
description: Analyse historical sales signal and compute baseline weekly run rate
inputs: [historical_sales, product_category, store_id]
---
You are a demand analyst. Analyse the historical sales data below and
produce a baseline demand signal.

Store: {store_id}
Category: {product_category}
Historical sales (8 weeks): {historical_sales}

Compute:
1. Average weekly run rate
2. Trend (rising/flat/falling)
3. Coefficient of variation
4. Anomalies (>20% deviation)
```

**Same registry, same loader, same MCP server.** New domains add `.md` files; no code changes to the registry.

---

## MCP Server Integration

```bash
# Register retail skill catalog with Claude Code
SKILLS_DOMAIN=retail claude mcp add adv-multi-agent-retail \
    -- python -m adv_multi_agent.core.skills.mcp_server

# Same binary supports research, parole, retail via SKILLS_DOMAIN env
```

Available tools after registration:
- `list_skills` — names of all bundled skills
- `describe_skills` — names + descriptions
- `get_skill` — render the template
- `render_skill` — fill `{tokens}` with caller inputs

Skills are inert text until rendered — no execution surface.

---

<!-- _class: section -->

# 6. Output Surface

*What the buyer / manager receives*

---

## Demand: Buyer Checklist

After convergence, the workflow returns `result.metadata["buyer_checklist"]`:

```
[ ] Verify historical sales data for SKU-88210-MILK2PCT in store KRO-OH-0042
[ ] Confirm upcoming events and promotion dates are current
[ ] Cross-check weather forecast against latest NWS data
[ ] Validate lead time with supplier before placing order
[ ] Review forecast against category manager's weekly guidance
[ ] Approve replenishment order — AI output must not trigger auto-ordering
```

If any `ASSUMPTION FLAGS` were raised during iteration (even if resolved), a prepended warning row prompts re-verification of the resolution.

---

## Labor: Manager Checklist

After convergence, the workflow returns `result.metadata["manager_checklist"]`:

```
[ ] Verify staff availability for week of 2026-05-18
[ ] Confirm all shifts comply with state labor law requirements
[ ] Check total hours per employee against OT threshold
[ ] Verify budget: total estimated cost vs. approved labor budget
[ ] Review peak coverage for projected high-traffic periods
[ ] Publish schedule — AI output must not go directly to employees
```

If any `COMPLIANCE FLAGS` were raised during iteration, a prepended warning row prompts re-verification of every flagged rule.

---

## Programmatic Disclaimer

Both workflows append a disclaimer in **code**, not in a prompt template:

```python
return WorkflowResult(
    output=f"{output}\n\n---\n\n{_DISCLAIMER}",
    ...
)
```

```
⚠️  ADVISORY ONLY — This AI-generated forecast is not a purchase order.
A human buyer must review all assumptions independently and approve any
replenishment action. AI output must never trigger automated ordering.
```

The disclaimer cannot be removed by prompt injection or model output. It is added after the model call.

---

<!-- _class: section -->

# 7. Design Properties

*What carries over from core/*

---

## Inherited Safety Properties

`DemandForecastWorkflow` and `LaborSchedulingWorkflow` inherit from `BaseWorkflow`. All `core/` security properties apply unchanged:

| Property | Source | Behavior |
|---|---|---|
| API key redaction | `Config` `__repr__` / `safe_dict()` | Keys never appear in logs or repr |
| Path sandboxing | `safe_resolve_path` | All workspace files under `workspace_dir/` |
| Atomic persistence | `_internal.atomic_write` | Ledger + wiki writes are temp+fsync+rename |
| Prompt sanitization | `sanitize_for_prompt` | All caller-supplied text fenced before injection |
| Same-family warning | `Config.__post_init__` | UserWarning if executor + reviewer are same provider |
| Skill name validation | `SkillRegistry` | Regex + size cap, symlink rejection |

> Adding a domain does not expand the security surface. The domain inherits everything the core already guarantees.

---

## Domain-Specific Properties

| Property | Demand | Labor |
|---|---|---|
| Domain flag extractor | `_extract_assumption_flags` | `_extract_compliance_flags` |
| Convergence gate | `score ≥ threshold AND not assumption_flags` | `score ≥ threshold AND not compliance_flags` |
| Revision verb | "remove or ground" | "fix, do not note" |
| Disclaimer text | "Not a purchase order" | "Not a published schedule" |
| Checklist key | `metadata["buyer_checklist"]` | `metadata["manager_checklist"]` |
| Metadata flag key | `metadata["assumption_flags"]` | `metadata["compliance_flags"]` |

The pattern parity is intentional — adding a third retail workflow (markdown optimization, supplier negotiation) follows the same recipe.

---

<!-- _class: section -->

# 8. PRODUCTION_GAPS

*What this is not, by design*

---

## Demand — PRODUCTION_GAPS

| Gap | Why it matters |
|---|---|
| Live POS data integration | `historical_sales` is free-text; production requires store transaction system feed |
| Actuarial demand baseline | ML model (Prophet, LightGBM) should anchor the forecast; LLM adjusts the residual, not the baseline |
| Supplier API integration | `lead_time_days` should come from EDI / supplier API in real time |
| Cost model | Stockout and overstock costs from actual margin + spoilage data, not qualitative assessment |
| Buyer approval gate enforced in code | Replenishment must not be placed automatically |
| Dedicated third-model assumption auditor | Single-stage reviewer folds quality + assumption audit; ARIS §3.1 specifies a three-stage cascade. Production needs a separately configured auditor (different family from BOTH executor and reviewer) |

Listed verbatim in `demand_forecasting.py` module docstring. The library does not pretend to be a replenishment system; it is a reasoning scaffold.

---

## Labor — PRODUCTION_GAPS

| Gap | Why it matters |
|---|---|
| HCM integration | `staff_roster` is free-text; production requires HR / scheduling system feed for real availability |
| Automated labor-law lookup by jurisdiction | `state_labor_law_notes` is caller-supplied; production needs a rules database |
| Shift-swap and time-off handling | Not modeled here — production schedulers handle approvals and pickup |
| Payroll system write-back | Schedule must not auto-publish; downstream payroll integration is out of scope |
| Manager approval gate enforced in code | Schedule must not go directly to employees |
| Dedicated third-model compliance auditor | Legal interpretation of statutes by a single LLM is not defensible. ARIS §3.1 specifies a three-stage cascade; production needs a separately configured compliance auditor model |

Listed verbatim in `labor_scheduling.py` module docstring. The library is a teaching example — not a workforce-management product.

---

<!-- _class: section -->

# 9. Status & Adoption

*Where this is in the lifecycle*

---

## Status

| Property | Status |
|---|---|
| `DemandForecastWorkflow` + tests | ✅ Complete (11 unit tests) |
| `LaborSchedulingWorkflow` + tests | ✅ Complete (11 unit tests) |
| 9 retail skill templates | ✅ Complete |
| Examples with synthetic Kroger data | ✅ Complete |
| Spec + plan in repo | ✅ Complete |
| Live operational integration | ❌ PRODUCTION_GAP |
| Pilot study | ❌ Not started |

Test suite total: 203 tests (160 research + 21 parole + 22 retail). All green. mypy strict. ruff clean.

---

## Who It Is For

**Retail data and operations teams** evaluating LLM augmentation for replenishment and scheduling. The convergence gates and ledger provide a structured audit trail.

**Engineering teams** adding a new domain. The retail domain is the second reference implementation after parole — together they show the recipe for any high-stakes, data-rich domain.

**Researchers** studying cross-model adversarial pairs in operational decisions where ground truth is observable post-hoc (forecast accuracy, compliance violations).

---

## Next Actions

| Action | Owner | Notes |
|---|---|---|
| POS / HCM integration adapters | Engineering | Replace free-text inputs with system feeds |
| Actuarial demand baseline | Data Science | LLM provides residual adjustments |
| Labor-law rule library | Legal + Engineering | Per-jurisdiction OT, break, minor-labor, predictive-scheduling |
| External signal feeds | Engineering | NWS weather, BLS unemployment, holiday calendar |
| Order / schedule approval gate | Engineering | Code-enforced human sign-off |
| Pilot study | Operations | Single store, single category, 4-week shadow run before production |

---

<!-- _class: lead -->

# Thank you

Questions?

&nbsp;

Repo: github.com/gmanch94/adv-multi-agent
Brief: docs/retail-executive-brief.md
Spec: docs/superpowers/specs/2026-05-13-retail-domain-design.md
