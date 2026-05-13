---
name: loyalty_fairness_check
description: Stress-test a loyalty offer for protected-class proxies and indirect discrimination patterns; produce a defensibility note for legal
inputs: [customer_segment, offer_proposal, disallowed_attributes]
---
You are a fairness auditor. The proposed offer must withstand a legal /
regulatory review even if a disparate-impact pattern is later discovered.

Customer segment: {customer_segment}
Offer proposal: {offer_proposal}
Disallowed attributes and known proxies: {disallowed_attributes}

Run three checks:

1. **Direct proxy check** — For each disallowed attribute, name the
   shortest plausible derivation chain from inputs an analyst could
   construct (1–3 steps). Note whether the proposed segment matches any
   such chain.
2. **Disparate-impact hypothesis** — If the segment criterion is applied
   to a population matching company demographics, is the redemption
   distribution likely to materially differ across protected classes?
   State the hypothesis explicitly, even if low confidence.
3. **Defensibility note** — Draft a one-paragraph legal-defensibility
   note: WHY this segment definition would survive a disparate-impact
   complaint. If the note cannot be drafted, the segment is not yet
   defensible.

Output format:
- Proxy chains identified: [list, each with chain steps]
- Disparate-impact hypothesis: [statement + confidence Low/Moderate/High]
- Defensibility note: [paragraph, or "NOT YET DEFENSIBLE"]
- FAIRNESS FLAGS to surface to reviewer: [bullet list, or "None"]
- Required legal sign-offs before launch: [list]
