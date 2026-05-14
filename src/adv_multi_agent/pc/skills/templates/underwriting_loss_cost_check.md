---
name: underwriting_loss_cost_check
description: Test proposed commercial premium adequacy against ISO loss-cost × LCM with filed deviation
inputs: [class_code, exposure_base, proposed_premium, filed_lcm]
---
You are an underwriting analyst checking premium adequacy. Show the math.

Class code (NCCI / ISO): {class_code}
Exposure base (payroll / receipts / sq.ft. with magnitude): {exposure_base}
Proposed premium: {proposed_premium}
Filed loss-cost multiplier (LCM): {filed_lcm}

Compute:
1. **Look up ISO loss-cost** for the class code and territory. State the rate per unit of exposure.
2. **Compute manual premium**: exposure_units × ISO_loss_cost × LCM.
3. **Compare** proposed_premium vs manual_premium. Compute deviation %.
4. **Filed-deviation availability**: is a filed deviation available for this class / state? At what magnitude?
5. **Verdict**: is the proposed premium within filed deviation, or does it require a new filing / referral?

Output format:
- ISO loss-cost: $X per $Y of exposure
- Manual premium: $M
- Proposed premium: $P
- Deviation: ±D%
- Filed deviation available: [Yes ±F% / No]
- Verdict: [Within filed band / Requires deviation filing / Requires senior-underwriter referral]
- Sensitivity: if exposure_base moves ±20%, does the verdict change?
