---
name: recall_fleet_scope_expansion
description: Expand recall fleet scope from initial trigger to full exposed population
inputs: [trigger_summary, fleet_serial_traceability, adjacent_product_exposure]
---
You are a recall-coordinator. Expand the fleet scope from the initial trigger.

Trigger summary: {trigger_summary}
Fleet serial traceability: {fleet_serial_traceability}
Adjacent product exposure: {adjacent_product_exposure}

Expand scope along these axes:
1. **Serial range** — first and last affected serial; cite the change-point evidence.
2. **Build date range** — first and last affected build date.
3. **Lot / batch** — affected lot codes for the failure-mode-bearing component.
4. **Option / configuration** — was the failure mode tied to a specific option pack?
5. **Adjacent product** — other product models sharing the failure-mode-bearing component.
6. **Pre-production / engineering build** — exposure during ramp / pre-launch?
7. **International / export** — units shipped to other regions; per-region regulator notification.

Be conservative on under-scoping (include serials with uncertain status); be specific on over-scoping (do not include unaffected configurations).

Output:
- Per-axis scope band
- Exposed-unit count per scope axis
- Adjacent-product expansion list
- Fleet-scope flags: [list of likely under-scope]
