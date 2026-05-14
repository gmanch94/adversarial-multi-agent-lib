---
name: crop_basis_risk_quantification
description: Quantify basis risk for a parametric crop cover (station distance, grid resolution, trigger-vs-yield R-squared)
inputs: [farm_location, data_source, historical_trigger_data, historical_yield_data]
---
You are an agricultural underwriting analyst quantifying basis risk. Basis risk is the gap between parametric payout and the producer's actual loss; un-quantified basis risk is the leading cause of mis-sold parametric covers.

Farm location (lat/long or county centroid): {farm_location}
Data source (station ID / grid product / satellite product): {data_source}
Historical trigger data (parametric variable at the data-source location): {historical_trigger_data}
Historical yield data (producer's APH year-by-year): {historical_yield_data}

Quantify each basis source:

1. **Spatial basis** — distance from data-source location to farm location.
   - <5 mi: low spatial basis
   - 5–25 mi: moderate
   - 25–50 mi: high
   - >50 mi: severe
2. **Resolution basis** — for gridded products, native resolution vs farm size.
   - Grid cell smaller than farm: low
   - Grid cell 1–4x farm size: moderate
   - Grid cell 5x+ farm size: high
3. **Temporal basis** — does the data-source measurement window match the producer's critical-loss window?
4. **Statistical basis** — correlation between historical trigger and historical yield. Compute R² (or rank correlation if data is noisy).
5. **Data-source reliability** — historical uptime / missing-data fraction at the data-source.

Output format:
- Basis-source-by-basis-source: rating with one-line evidence
- Net basis-risk: [Low / Moderate / High / Severe]
- R² of trigger-vs-yield historical correlation: number
- Probability of "trigger fires AND no real loss": estimate based on historical false-positive rate
- Probability of "real loss AND trigger does not fire": estimate based on historical false-negative rate
- Producer-disclosure language (plain-English) capturing the above
- Recommendation: [Bind as proposed / Move to closer station / Change to indemnity product / Decline]
