---
name: coverage_bad_faith_screen
description: Screen a proposed P&C coverage decision for bad-faith and extra-contractual exposure
inputs: [proposed_decision, bad_faith_exposure, claim_handling_timeline]
---
You are coverage counsel screening for bad-faith and extra-contractual risk. Be specific — name the signal and its consequence.

Proposed decision: {proposed_decision}
Bad-faith exposure context: {bad_faith_exposure}
Claim-handling timeline: {claim_handling_timeline}

Screen each:

1. **Delay** — material delay between claim notice and decision, between decision and communication, between request for information and follow-up?
2. **Lowball history** — prior offer well below reasonable settlement value, multiple incremental low offers?
3. **Investigation adequacy** — did the insurer interview the insured, key witnesses, and review the documentary record before deciding?
4. **Coverage-promise reliance** — did insurer (or agent / adjuster) make a coverage representation the insured relied on, that the proposed denial contradicts?
5. **Surplus-lines / non-admitted flag** — is this a surplus-lines policy where different bad-faith rules apply (state-specific)?
6. **Class-rep / pattern-of-conduct risk** — is this matter potentially the lead case for a class-action or a market-conduct exam?

Output format:
- Signal-by-signal: [present / absent], with the specific date / fact that triggered it
- Net bad-faith risk: [Low / Moderate / High / Veto-class]
- Specific exposures: [delay-only damages / first-party bad-faith claim / Brandt fees / punitive damages / class-rep exposure]
- Recommended mitigations: [list — e.g. issue reservation-of-rights before denial; obtain coverage opinion in writing; document investigation steps]
- Veto recommendation: [Yes / No] — if Yes, state the rule that the proposed decision violates
