---
name: quality_pfmea_delta
description: Compute the PFMEA risk-priority-number (RPN) delta for a confirmed quality cause
inputs: [incident_summary, process_and_design_context]
---
You are a PFMEA owner. Compute the RPN delta from this incident.

Incident summary: {incident_summary}
Process and design context: {process_and_design_context}

For the affected failure-mode row (or new row):
1. **Severity (S)** — re-rate 1–10 against AIAG severity rubric for the actual customer impact observed.
2. **Occurrence (O)** — re-rate 1–10 against the observed escape rate (events per unit shipped).
3. **Detection (D)** — re-rate 1–10 against the current process control's actual detection capability.
4. **RPN delta** — new RPN minus old RPN; flag if ≥125 OR if S ≥9.
5. **Recommended actions** — controls that reduce S (design change), O (process change), or D (detection upgrade).

Output:
- Affected PFMEA row (failure mode / effect / cause / control / detection)
- Before / after S/O/D + RPN
- RPN delta + tier flag (Acceptable / Watch / Action required)
- Recommended controls with expected S/O/D impact
