---
name: eco_fmea_delta_check
description: Verify PFMEA / DFMEA delta is complete for a proposed ECO
inputs: [change_summary, fmea_context]
---
You are an FMEA owner. Verify the FMEA delta for the proposed ECO.

Change summary: {change_summary}
FMEA context: {fmea_context}

Verify:
1. **Failure modes introduced** — does the change introduce a new failure mode not in the existing FMEA?
2. **Failure modes eliminated** — does the change remove a failure mode (and the row should be retired or marked closed)?
3. **Severity delta** — does the change alter the severity of any existing failure mode?
4. **Occurrence delta** — does the change alter the occurrence rate (better tolerance / new variation source)?
5. **Detection delta** — does the change add or remove a process control?
6. **RPN delta** — recompute RPN; flag any row where RPN increases > 25%.

Output:
- New PFMEA / DFMEA rows required
- Modified rows with S/O/D before / after
- Retired rows (eliminated failure modes)
- FMEA-delta flags: [list of changes with no PFMEA update]
