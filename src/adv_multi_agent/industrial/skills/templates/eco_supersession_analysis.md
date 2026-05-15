---
name: eco_supersession_analysis
description: Analyse form / fit / function supersession rules for affected part numbers in an ECO
inputs: [change_summary, affected_part_numbers, f3_analysis]
---
You are a configuration-management engineer. Analyse supersession for each affected part number.

Change summary: {change_summary}
Affected part numbers: {affected_part_numbers}
F/F/F analysis: {f3_analysis}

For each affected part number:
1. **Form** — physical envelope (size, weight, attach features) — interchangeable?
2. **Fit** — mating interfaces, fastener pattern, harness pinout, alignment features — interchangeable?
3. **Function** — performance characteristics, calibration, software-compatibility — interchangeable?
4. **Supersession direction** — interchangeable in both directions / one-way (new replaces old, not vice versa) / not interchangeable.
5. **Effectivity basis** — date-effective / serial-effective / lot-effective / on-order-effective.
6. **Service-parts implication** — does the catalog need a separate service part number for legacy?

Output:
- Per-part supersession verdict + direction
- Effectivity basis per part
- Service-parts catalog update list
- Supersession flags: [list of weak / unsupported F/F/F claims]
