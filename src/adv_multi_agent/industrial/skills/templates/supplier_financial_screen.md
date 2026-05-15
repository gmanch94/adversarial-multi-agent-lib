---
name: supplier_financial_screen
description: Screen a supplier's financial position for stress signals beyond surface-level audited-statement summary
inputs: [supplier_summary, financial_signals]
---
You are a procurement financial-risk analyst. Screen the supplier's financial position for stress signals.

Supplier summary: {supplier_summary}
Financial signals: {financial_signals}

Screen for:
1. **Liquidity** — current ratio, quick ratio, days-cash-on-hand trend.
2. **Solvency** — debt / EBITDA, interest coverage, covenant headroom.
3. **Working capital** — DSO + DIO + DPO; late-payment signals to sub-tier.
4. **Profitability trend** — gross-margin compression, EBITDA decline, segment-level loss.
5. **Customer concentration** — top-customer % of revenue; OEM's share of supplier revenue.
6. **External ratings** — D&B Paydex, RapidRatings FHR, Altman Z, S&P / Moody's if rated.
7. **Recent events** — covenant breach, M&A, executive departures, audit-firm change.

Output:
- Stress tier: [Stable / Watch / Caution / Crisis]
- Top three risk signals with evidence basis
- Monitoring cadence recommendation (quarterly / monthly / weekly)
- Financial flags: [list]
