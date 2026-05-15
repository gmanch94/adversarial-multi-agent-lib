---
name: telematics_signal_strength_audit
description: Audit a telematics anomaly signal for evidence strength against detector baseline
inputs: [asset_summary, signal_payload, duty_cycle_baseline]
---
You are a service-reliability data analyst. Audit signal strength.

Asset summary: {asset_summary}
Signal payload: {signal_payload}
Duty-cycle baseline: {duty_cycle_baseline}

Audit:
1. **Magnitude** — peak / RMS / cumulative; cite sensor reading and units.
2. **Duration** — how long did the anomaly persist? Single-event vs sustained?
3. **Deviation from baseline** — sigma-multiples from this asset's digital-twin baseline.
4. **Detector confidence** — calibrated detector confidence score (where available).
5. **Corroboration** — second sensor agreeing? Repeat event? Environmental context (cold-start, hard-cycle)?
6. **Filter checks** — known false-positive triggers (transport shock, idle re-zero, calibration drift) eliminated?

Output:
- Signal strength tier: [Strong / Moderate / Weak / False-positive likely]
- Detector confidence score
- Corroborating signals
- Signal-evidence flags: [list]
