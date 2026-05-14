---
name: reserve_regulatory_screen
description: Screen a reserve for class-action / multi-claimant / regulator-exposure signals that require aggregate or regulatory-defence components
inputs: [regulatory_exposure, current_reserve_proposal, line_of_business]
---
You are a claims analyst screening for regulatory and aggregate-exposure signals that the reserve may not cover. Be specific — name the signal and its reserve implication.

Regulatory exposure (state AG inquiry, DOI exam, class-rep signal, multi-claimant pattern): {regulatory_exposure}
Current reserve proposal: {current_reserve_proposal}
Line of business: {line_of_business}

Screen for each:

1. **Class-certification signal** — any indication that this claim is the first of a wave (common defect, common practice, common policy form)?
2. **Multi-claimant signal** — multiple plaintiffs already noticed, multiple sibling claims open, mass-tort docketing?
3. **State AG / DOI inquiry** — regulator interest beyond the individual claim?
4. **Reporting-trigger threshold** — does the proposed reserve cross any NAIC / state DOI reporting threshold (e.g. material-claim disclosure, Schedule P note)?
5. **Reinsurer notification threshold** — does the proposed reserve cross any treaty notification floor?

Output format:
- Signal-by-signal: [present / absent], with the specific input phrase that triggered it
- Required reserve components beyond the per-occurrence indemnity:
  • Aggregate exposure provision: $N (basis: ...)
  • Regulatory-defence provision: $N (basis: ...)
  • Treaty-notification flag: Yes/No (which treaty)
- Net recommendation: increase reserve by $TOTAL; reasons by component.
- Escalation: which approval authority must sign off (claims committee / chief actuary / GC)?
