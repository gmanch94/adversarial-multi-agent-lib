---
name: trial_review
description: Reviewer criteria for clinical-trial eligibility assessment; five-dimension scoring with dedicated BIAS DETECTION dimension (JAMA 2019 cardiology RCT under-representation) and D-HEALTH-4 veto criteria for safety exclusion, protected-class bias, or evidence contradiction
inputs:
  - output
---
Evaluate this clinical-trial eligibility assessment on five dimensions. Score each 0–10.

1. PROTOCOL FIDELITY (30%) — CRITICAL
   Every eligibility statement must map to a protocol section number. Do not
   paraphrase; cite the protocol section directly. Penalise any eligibility
   claim that lacks a protocol-section reference.
   Flag gaps under ELIGIBILITY FLAGS:.

2. BIAS DETECTION (25%) — CRITICAL
   Scrutinise whether any protected-class attribute — race, ethnicity, sex,
   age (beyond age-range inclusion criteria with clinical justification),
   disability — is used as a determinative factor in eligibility without
   explicit protocol-specified clinical justification.
   Cite the JAMA 2019 systematic review documenting under-representation of
   racial/ethnic minorities and women in cardiology RCTs (Duma et al., JAMA
   Cardiol. 2019;4(3):211-219; analogous patterns documented in oncology and
   neurology RCTs). Any eligibility reasoning that echoes historical
   under-representation patterns must be flagged — the reviewer must veto
   rather than approve bias-driven exclusion.
   Flag gaps under BIAS FLAGS:.

3. EVIDENCE GROUNDING (20%) — CRITICAL
   biomarker_status, lab values, and prior_treatments must be cited directly
   from the input fields, not inferred from free-text summaries or outside
   knowledge. Do not import data not present in the request.
   Flag gaps under EVIDENCE FLAGS:.

4. SAFETY EXCLUSION COMPLETENESS (15%)
   Life-threatening exclusion criteria — organ dysfunction per protocol
   thresholds (eGFR, LVEF, bilirubin, creatinine), prohibited concomitant
   medications, active infection per protocol — must be verified explicitly
   against the protocol and biomarker_status. Penalise assessments that assert
   "no exclusions" without checking each life-threatening exclusion class.
   Flag life-threatening gaps under ELIGIBILITY FLAGS:.

5. DECISION CLARITY (10%)
   The final determination must be one of: eligible / ineligible / requires
   review. The rationale must be traceable to a protocol section number.
   Ambiguous determinations must be flagged.

VETO CRITERIA (independent of score)
End your review with a REVIEWER VETO: line containing a verbatim directive
if and only if at least one of the following holds:
  • Patient meets a life-threatening exclusion criterion (organ dysfunction
    per protocol thresholds, prohibited concomitant medication, active
    infection per protocol) but the draft marks patient eligible. Per
    ICH-GCP and IRB protocol governance, enrolling a patient meeting
    safety exclusion is a serious deviation.
  • Protected-class attribute (race, ethnicity, sex, age, disability)
    appears to be a determinative exclusion factor without protocol-
    specified clinical justification. Cf. JAMA 2019 systematic review on
    cardiology RCT under-representation (Duma et al., JAMA Cardiol.
    2019;4(3):211-219); similar patterns documented in oncology / neurology.
    The reviewer must veto rather than approve bias-driven exclusion.
  • Eligibility determination contradicts primary evidence in
    protocol_summary or biomarker_status (e.g. patient marked eligible
    despite biomarker-status mismatch with inclusion criteria).
Otherwise: "REVIEWER VETO: None".

FORMAT NOTE (L-PC-2): do not begin a veto-directive continuation line with
  "Overall", "Key issues", or a "#" markdown header — the parser uses those
  as stop markers. Write all continuation lines in free prose.

Overall score = weighted average.
Score >= 8.0 AND zero BIAS FLAGS AND zero ELIGIBILITY FLAGS AND zero
EVIDENCE FLAGS AND no VETO: assessment is ready for PI and IRB sign-off.
Otherwise: requires revision (or escalates on veto).

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  BIAS FLAGS: [bullet list, or "None detected"]
  ELIGIBILITY FLAGS: [bullet list, or "None detected"]
  EVIDENCE FLAGS: [bullet list, or "None detected"]
  REVIEWER VETO: <verbatim directive, or "None">
