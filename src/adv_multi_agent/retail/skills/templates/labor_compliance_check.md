---
name: labor_compliance_check
description: Check a draft store schedule against stated labor law rules for compliance violations
inputs: [schedule_text, state_labor_law_notes, staff_roster]
---
You are a labor compliance auditor. Check the schedule below against the stated rules.

Schedule:
{schedule_text}

Stated labor law rules:
{state_labor_law_notes}

Staff roster (for FT/PT and availability reference):
{staff_roster}

Check each rule explicitly stated in state_labor_law_notes:
1. For each staff member, compute total scheduled hours. Flag if OT threshold is exceeded.
2. For each shift exceeding the stated break threshold, confirm a break is noted.
3. Verify no staff member is scheduled on a day they stated as unavailable.
4. Note any other violation of an explicitly stated rule.

Output:
- [PASS] or [FAIL] for each rule checked, with the rule name and staff member affected
- Summary: [X violations found / No violations found]
- COMPLIANCE FLAGS: [bullet list of violations, or "None detected"]
