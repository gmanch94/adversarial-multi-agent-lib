# Retail Domain Design Spec
*2026-05-13*

## Overview

New `retail/` domain alongside `parole/`. Two workflows: demand forecasting and labor scheduling. Teaching examples with synthetic data. Mirrors parole pattern exactly — no new abstractions.

---

## Structure

```
src/adv_multi_agent/retail/
  __init__.py
  workflows/
    __init__.py
    demand_forecasting.py     # ForecastRequest + DemandForecastWorkflow
    labor_scheduling.py       # SchedulingRequest + LaborSchedulingWorkflow
  skills/
    __init__.py
    templates/                # 9 templates, flat, prefixed by domain
      demand_signal.md
      demand_seasonality_audit.md
      demand_stockout_risk.md
      demand_weather_impact.md
      demand_unemployment_rate.md
      labor_schedule_draft.md
      labor_compliance_check.md
      labor_coverage_audit.md
      labor_unemployment_rate.md

examples/retail/
  __init__.py
  demand_forecasting.py       # synthetic ForecastRequest, runs workflow
  labor_scheduling.py         # synthetic SchedulingRequest, runs workflow
```

---

## Workflow 1: Demand Forecasting

### Input dataclass — `ForecastRequest`

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

### Executor task
Produce a structured replenishment recommendation with sections:
- Demand Signal Analysis
- Forecast (units/week, 4-week horizon)
- Replenishment Recommendation (order qty, timing, supplier)
- Key Assumptions
- Evidence Gaps
- Claims (one per line, `[Source: <field>] <claim>`)

### Reviewer criteria
Five dimensions, score 0–10:
1. **Forecast Grounding** (30%) — Is the forecast anchored to historical signal? Are adjustments to baseline justified?
2. **Assumption Audit** (25%) — Are all assumptions (seasonality, weather, events) explicit, stated, and proportionate? Flag under `ASSUMPTION FLAGS:`.
3. **Risk Balance** (25%) — Does the recommendation balance stockout risk vs. overstock/spoilage? Is safety stock reasoning sound?
4. **Completeness** (10%) — Are data gaps noted? Is confidence expressed appropriately?
5. **Actionability** (10%) — Is the order recommendation specific (units, date, supplier)?

Convergence: score ≥ 7.5 **and** zero `ASSUMPTION FLAGS`.

### Production gaps (in module docstring)
1. Live POS data integration (historical_sales is free-text here)
2. Actuarial demand models — ML baseline, not LLM intuition
3. Supplier API integration for real lead times
4. Automated stockout/overstock cost calculation
5. Human buyer approval gate before orders are placed

---

## Workflow 2: Labor Scheduling

### Input dataclass — `SchedulingRequest`

| Field | Type | Description |
|---|---|---|
| `store_id` | `str` | Store identifier |
| `week_start` | `str` | ISO date of week start (Monday) |
| `projected_traffic` | `str` | Expected customer volume by day + peak hours |
| `staff_roster` | `str` | Names, roles, availability constraints, FT/PT status |
| `labor_budget` | `str` | Weekly labor budget in dollars |
| `local_events` | `str` | Events that affect foot traffic (game days, concerts) |
| `state_labor_law_notes` | `str` | Applicable rules: minor labor, overtime threshold, break requirements |
| `unemployment_rate` | `str` | Local unemployment rate + trend (affects hiring pool / turnover) |

### Executor task
Produce a structured weekly schedule with sections:
- Schedule (day-by-day, shift assignments per role)
- Coverage Analysis
- Labor Cost Estimate
- Compliance Notes
- Fairness Notes
- Evidence Gaps
- Claims

### Reviewer criteria
Five dimensions, score 0–10:
1. **Coverage** (30%) — Are all peak hours adequately staffed by role? Are gaps identified?
2. **Compliance** (25%) — Flag any violation of stated labor laws under `COMPLIANCE FLAGS:`: minor labor rules, overtime thresholds, mandatory breaks, rest periods.
3. **Cost Efficiency** (20%) — Is overtime minimized? Is the schedule within labor budget?
4. **Fairness** (15%) — Are shifts distributed equitably? Are availability constraints honored?
5. **Actionability** (10%) — Is the schedule specific enough to post on the break room board?

Convergence: score ≥ 7.5 **and** zero `COMPLIANCE FLAGS`.

### Production gaps (in module docstring)
1. Live HCM system integration (staff_roster is free-text here)
2. Automated labor law lookup by jurisdiction (state_labor_law_notes is caller-supplied)
3. Shift-swap and time-off request handling
4. Payroll system write-back
5. Manager approval gate before schedule is published

---

## Skill Templates (9, flat, prefixed)

| File | Domain | Purpose |
|---|---|---|
| `demand_signal.md` | Demand | Analyze historical sales + trend |
| `demand_seasonality_audit.md` | Demand | Challenge seasonality assumptions |
| `demand_stockout_risk.md` | Demand | Evaluate stockout vs. spoilage tradeoff |
| `demand_weather_impact.md` | Demand | Factor weather forecast into demand adjustment |
| `demand_unemployment_rate.md` | Demand | Assess unemployment rate as consumer spending signal |
| `labor_schedule_draft.md` | Labor | Draft weekly schedule from roster + traffic |
| `labor_compliance_check.md` | Labor | Verify schedule against stated labor law rules |
| `labor_coverage_audit.md` | Labor | Audit peak hour coverage by role |
| `labor_unemployment_rate.md` | Labor | Assess unemployment rate as staffing pool / wage pressure signal |

---

## Examples

Each example file constructs a realistic synthetic input object and runs the workflow end-to-end. Output printed to stdout. No live API calls beyond the configured model providers.

---

## Decisions

- Approach A (strict domain separation) chosen — no shared retail base class, no abstraction beyond what parole already provides.
- Flat skill templates dir with prefixes — avoids nested `demand/` and `labor/` subdirs, keeps parity with parole.
- Convergence gates mirror parole: score threshold + zero domain-specific flags (ASSUMPTION FLAGS / COMPLIANCE FLAGS).
- Synthetic data only — no live Kroger API integration.
