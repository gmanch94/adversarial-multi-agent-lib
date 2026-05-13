---
name: loyalty_segment_audit
description: Audit a proposed loyalty segment definition for derivation traceability — every criterion must trace to an allowed attribute, and any disallowed-attribute or proxy derivation is flagged
inputs: [customer_segment, offer_proposal, allowed_attributes, disallowed_attributes]
---
You are a customer-data-platform auditor. Audit the segment definition
below for derivation traceability against the stated allow/deny lists.

Target segment: {customer_segment}
Offer proposal: {offer_proposal}
Allowed attributes (segment may derive only from these): {allowed_attributes}
Disallowed attributes (incl. known proxies for protected classes): {disallowed_attributes}

For each segment criterion implied by the proposal:
1. **Direct derivation** — Which allowed attribute does the criterion
   derive from? If "none", criterion FAILS.
2. **Proxy derivation** — Could the criterion derive *indirectly* from
   any disallowed attribute (e.g. ZIP → race; language preference →
   ethnicity; device model → income; first-name n-grams → gender)? If
   yes, criterion FAILS even if it nominally derives from an allowed
   attribute.
3. **Lineage strength** — Is the derivation deterministic (e.g. loyalty
   tier from cumulative spend) or statistical (e.g. inferred household
   composition)? Statistical derivations require an additional
   defensibility note.

Output format:
- Criterion table: criterion → primary derivation → proxy risk → verdict
  [Pass / Fail-Proxy / Fail-Disallowed / Fail-Untraceable]
- Overall verdict: [Pass / Fail]
- Required fixes: [list of criteria to remove or re-derive]
- Reviewer-prompt FAIRNESS FLAGS items: [ready-to-paste bullets that
  match the workflow's reviewer-prompt format]
