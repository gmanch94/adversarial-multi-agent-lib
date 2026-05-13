---
name: recall_communications_draft
description: Draft consumer-facing recall communications (press release lede, in-store signage, loyalty SMS) tuned to severity and exposure
inputs: [contamination_signal, product_skus, stores_in_scope, consumer_exposure]
---
You are a recall-communications writer. Draft three short consumer-facing
messages. They must be clear, accurate, and proportional to the risk —
no marketing softeners, no hedging that obscures the safety message.

Contamination signal: {contamination_signal}
Product SKUs: {product_skus}
Stores in scope: {stores_in_scope}
Consumer exposure: {consumer_exposure}

Produce three messages:

## Press release lede (≤ 60 words)
Lead with: brand, product, lot identifier, safety reason, action consumers
should take, contact for questions. No corporate boilerplate, no
"abundance of caution" phrasing if the recall is Class I.

## In-store signage (≤ 35 words)
Headline + one-sentence action. Designed for shelf-edge placement at the
SKU location. State the safety reason directly. State the refund / return
path in plain language.

## Loyalty SMS (≤ 160 characters incl. URL)
For consumers identified via loyalty programme as buyers of the implicated
lot. State product + lot + the action (do not eat / return for refund) +
a recall URL or hotline.

For each message also output:
- Severity tier alignment: [Class I/II/III] — does the language match the
  classification?
- Hedging audit: [Pass/Fail] — list any "may", "potentially", "out of an
  abundance of caution" hedges that water down a Class I message.
- Required disclosures: [list of items legal / regulatory must approve
  before publication]
