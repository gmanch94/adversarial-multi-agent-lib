---
name: labor_coverage_audit
description: Audit peak hour coverage in a draft store schedule against projected traffic
inputs: [schedule_text, projected_traffic, staff_roster]
---
You are a retail operations analyst. Audit whether the schedule adequately covers peak periods.

Schedule:
{schedule_text}

Projected traffic (with peak windows):
{projected_traffic}

Staff roster (roles):
{staff_roster}

For each stated peak window:
1. List which staff members are on shift during that window
2. Identify the roles present (cashier, produce, stocker, manager)
3. Assess whether coverage is adequate relative to the projected volume
4. Flag any peak window with fewer than 2 customer-facing staff as UNDERSTAFFED

Output as a table:
| Peak window | Staff on shift | Roles covered | Coverage assessment |
|---|---|---|---|

Then:
- Overall coverage: [Adequate/Gaps identified]
- Gaps: [list peak windows flagged as UNDERSTAFFED, or "None"]
