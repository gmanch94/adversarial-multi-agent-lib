---
name: makebuy_external_bid_normalisation
description: Normalise external supplier bids for a make-vs-buy review (currency, MOQ, Incoterm, freight, duty, tooling amortisation)
inputs: [external_bid_summary, component_summary, strategic_constraints]
---
You are a sourcing analyst. Normalise the external bid against the in-house should-cost baseline.

External bid summary: {external_bid_summary}
Component summary: {component_summary}
Strategic constraints: {strategic_constraints}

Normalise each bid:
1. **Currency + FX** — convert to OEM functional currency at forward rate over program horizon.
2. **MOQ + run quantity** — re-state unit price at OEM's actual annual demand.
3. **Incoterm** — restate at common Incoterm (EXW / FCA / DDP); add the freight + duty delta.
4. **Freight + duty + brokerage** — lane-specific quote, not catalog.
5. **Tooling amortisation** — separate one-time + amortised-in-price components.
6. **Inventory carry** — pipeline + safety stock implied by lead-time delta.
7. **Quality + warranty exposure** — supplier escape rate + warranty term.

Output:
- Normalised landed cost per unit per supplier: $X
- Year-1 vs steady-state delta
- TCO ranking
- Hidden-cost flags: [list]
