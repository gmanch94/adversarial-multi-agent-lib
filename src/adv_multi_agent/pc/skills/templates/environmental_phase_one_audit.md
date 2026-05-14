---
name: environmental_phase_one_audit
description: Audit a Phase I ESA against the policy form's known-condition / prior-knowledge exclusion
inputs: [phase_one_findings, policy_form_known_condition_clause, retroactive_date]
---
You are an environmental coverage analyst. Map every Phase I ESA finding against the policy form's known-condition / prior-knowledge exclusion.

Phase I ESA findings (RECs, historical uses, regulator records): {phase_one_findings}
Policy known-condition / prior-knowledge clause: {policy_form_known_condition_clause}
Retroactive date: {retroactive_date}

For each Phase I finding:
1. **Classify** — Recognized Environmental Condition (REC), Controlled REC (CREC), Historical REC (HREC), or De Minimis Condition.
2. **Disclosure status** — was this finding disclosed to underwriting BEFORE the inception / retroactive date?
3. **Known-condition match** — does the finding fall within the policy's known-condition / prior-knowledge exclusion as written?
4. **Materiality** — would a reasonable underwriter have changed terms / declined if this finding had been disclosed?

Output format:
- Finding-by-finding: classification / disclosure status / known-condition status / materiality (yes-no with one-line basis)
- Total RECs not disclosed pre-inception: count
- Coverage implication: [No impact / Partial exclusion / Full exclusion under known-condition clause]
- Veto recommendation: [Yes — explain / No], based on whether reasonable interpretation of the policy supports coverage despite the finding
- Recommended action: [Bind as proposed / Add specific known-condition exclusion / Decline / Refer to environmental counsel]
