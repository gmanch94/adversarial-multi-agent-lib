---
name: reserve_venue_adjustment
description: Adjust a reserve anchor for venue jury propensity and defense posture
inputs: [reserve_anchor, venue, defense_posture]
---
You are a claims analyst adjusting a reserve anchor for venue posture. Show the math.

Reserve anchor (from comparables median): {reserve_anchor}
Venue (state + county + court): {venue}
Defense posture: {defense_posture}

Adjustments:
1. **Venue uplift / downlift** — classify the venue as plaintiff-friendly, neutral, or defense-friendly. Apply an uplift / downlift consistent with venue jury-verdict data (Jury Verdict Reporter classification or peer-county data). State the percentage.
2. **Comparative-fault reduction** — if defense_posture states a fault percentage attributable to the claimant or co-defendant, reduce the reserve by the appropriate share under the applicable state's comparative-fault rule (pure, modified-50, modified-51, or contributory).
3. **Contributory-negligence wipeout** — if the venue is a pure contributory-negligence state and claimant fault is non-zero, flag the possibility of zero indemnity and quantify the residual defence-cost-only exposure.

Output format:
- Venue classification: [Plaintiff-friendly / Neutral / Defense-friendly]
- Venue uplift / downlift: ±X% (basis: one-sentence justification)
- Fault adjustment: −Y% (basis: state rule + fault attribution)
- Adjusted reserve: $N
- Contributory-negligence wipeout risk: [Yes/No]; if Yes, residual defence reserve: $D
- Show the math: anchor × (1 + venue%) × (1 − fault%) = adjusted
