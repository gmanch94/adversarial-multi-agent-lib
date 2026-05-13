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
| Demand forecasting | **planned** | Executor signals weekly replenishment; reviewer challenges seasonality, external shocks. Failure = spoilage or stockouts |
| Labor scheduling | **planned** | Executor generates store schedules; reviewer flags labor law violations, overtime cost, coverage gaps |
| Inventory replenishment | candidate | Auto-order logic reviewed for supplier lead time assumptions |

---

## Retail — Commercial (`src/adv_multi_agent/retail/`)
> Pricing, supplier, and product decisions

| Scenario | Status | Notes |
|---|---|---|
| Promo / markdown optimization | candidate | Executor proposes promo depth + timing; reviewer challenges margin math, elasticity, competitor response |
| Supplier negotiation briefs | candidate | Executor drafts position + BATNA; reviewer stress-tests cost assumptions, alternatives |
| Private label product decisions | candidate | Executor proposes new SKU; reviewer challenges cannibalization, brand perception risk |

---

## Retail — Customer (`src/adv_multi_agent/retail/`)
> Personalization and loyalty

| Scenario | Status | Notes |
|---|---|---|
| Loyalty / personalization offers | candidate | Executor generates segment offer strategy; reviewer challenges margin erosion, gaming risk, income fairness |

---

## Retail — Safety & Compliance (`src/adv_multi_agent/retail/`)
> Irreversible or regulated decisions

| Scenario | Status | Notes |
|---|---|---|
| Food safety / recall scope | candidate | Executor assesses contamination risk + recall boundaries; reviewer challenges scope. Reviewer veto highest-stakes use case |

---

## Other Domains (future)

| Domain | Scenario | Status | Notes |
|---|---|---|---|
| Healthcare | Clinical trial eligibility | candidate | Bias-gate pattern from parole applies |
| Healthcare | Drug interaction flagging | candidate | Reviewer = cross-model safety check |
| Finance | Loan underwriting | candidate | Adversarial reviewer catches protected-class proxies |
| Finance | Fraud alert triage | candidate | Executor flags; reviewer challenges false-positive rate |
| Legal | Contract risk review | candidate | Executor summarizes risk; reviewer stress-tests omissions |
| HR | Performance review drafting | candidate | Bias-gate on protected attributes |

---

*Last updated: 2026-05-13*
