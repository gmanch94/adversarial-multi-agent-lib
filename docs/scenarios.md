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
| Private label product decisions | candidate | Executor proposes new SKU; reviewer challenges cannibalization, brand perception risk |

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
