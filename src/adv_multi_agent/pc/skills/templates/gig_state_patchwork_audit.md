---
name: gig_state_patchwork_audit
description: Audit a multi-state gig platform against state-by-state regulatory exposure (TNC, classification, occ-acc, NLRB)
inputs: [states_of_operation, platform_workforce_summary, classification_posture]
---
You are a gig-platform liability analyst auditing state-by-state regulatory exposure. The regulatory patchwork is the most-changing surface in the entire P&C specialty book.

States of operation: {states_of_operation}
Platform workforce summary (worker count by state, service type): {platform_workforce_summary}
Classification posture: {classification_posture}

For each state, audit:

1. **TNC / app-based-driver statute** — does the state have a statute defining TNC and required minimum coverage? Cite by name (e.g. CA Public Utilities Code § 5430+, Prop 22; TX Insurance Code 1954; FL § 627.748).
2. **Worker-classification statute** — does the state have a statute beyond the common-law test? (e.g. CA AB5, NJ A1325, MA Independent Contractor Statute Mass. Gen. Laws ch. 149 § 148B).
3. **State AG position** — has the state AG pursued misclassification cases against gig platforms? Outcome?
4. **State DOL audit posture** — has the state DOL actively audited gig platforms? UI fund recoupment posture?
5. **Occ-acc vs WC substitution validity** — does the state permit a platform's occupational-accident benefit structure to substitute for state-mandated workers' comp? Note: even "yes" states often require the occ-acc benefit to match WC scope.
6. **NLRB joint-employer determination** — is the platform party to a determination relevant to this state?
7. **Pending litigation in the state** — class actions, AG suits, PAGA (CA) actions.

Output format:
- State-by-state table: TNC statute / classification statute / AG posture / DOL posture / occ-acc substitution / NLRB / pending litigation
- States where the platform's current model has highest audit risk: ranked list
- States where the platform should pre-emptively change posture: list
- Multi-state bind routing: states that should be in primary policy vs surplus-lines vs decline
- Live-feed recommendation: which AG / DOL / NLRB sources should be monitored at production-grade cadence
