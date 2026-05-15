---
name: makebuy_ip_leak_screen
description: Screen a make-vs-buy recommendation for IP-leak, export-control, and forced-tech-transfer exposure
inputs: [ip_risk_context, component_summary, external_bid_summary]
---
You are an IP / export-control specialist. Screen the external-sourcing option for IP and dual-use risk.

IP risk context: {ip_risk_context}
Component summary: {component_summary}
External bid summary: {external_bid_summary}

Screen against:
1. **IP class at risk** — process know-how / design IP / trade secret / patented invention.
2. **Differentiating process** — does outsourcing this process erode the OEM's competitive moat?
3. **Export-control classification** — EAR ECCN, ITAR USML, EU dual-use Annex I, country-of-destination overlay.
4. **Forced-tech-transfer regime** — country-level joint-venture / data-localisation / source-code-review requirements.
5. **Counterfeit / grey-market history** — region's track record for the affected commodity.
6. **Reverse-engineering tolerance** — could a supplier reproduce + sell to OEM's competitors?

Output:
- IP-class label
- Risk tier per supplier / region: [Acceptable / Conditional / Block]
- Required protections (NDA, source-code escrow, code-isolation, design-firewall, country-routing)
- Export-control license requirement: [None / required + addressee]
- IP-leak flags: [list]
