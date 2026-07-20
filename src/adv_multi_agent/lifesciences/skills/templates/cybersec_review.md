---
name: cybersec_review
description: Reviewer criteria for a premarket device cybersecurity review; THREAT-MODEL + SBOM-GAP + PATCHABILITY flags
inputs:
  - output
---

Evaluate this premarket device cybersecurity review on five dimensions. Score each 0–10.

1. THREAT-MODEL COMPLETENESS (30%) — CRITICAL
   Does every attack surface (interfaces, data flows, trust boundaries) have a
   security control addressing its threats? Penalise a threat or attack surface
   with no addressing control. Flag under THREAT-MODEL FLAGS:.

2. SBOM & VULNERABILITY MANAGEMENT (25%) — CRITICAL
   Is the software bill of materials complete, and is every known component
   vulnerability resolved or risk-accepted with justification? Penalise a missing
   component or an unresolved known vulnerability. Flag under SBOM-GAP FLAGS:.

3. PATCHABILITY / LIFECYCLE (20%) — CRITICAL
   Does every component that will need security patches over the device lifecycle
   have a field-update path? Penalise a component with no update mechanism. Flag
   under PATCHABILITY FLAGS:.

4. SECURITY-CONTROL ADEQUACY (15%)
   Are the security controls (authentication, encryption, integrity) proportionate
   to risk and linked to safety/essential performance? Penalise controls not
   matched to the risk.

5. ACTIONABILITY (10%)
   Is each finding specific enough for the security team to act on (which surface,
   which component, which control)? Vague findings should be penalised.

Overall score = weighted average.
Score >= 7.5 AND zero THREAT-MODEL FLAGS AND zero SBOM-GAP FLAGS AND zero
PATCHABILITY FLAGS: ready for Product Security sign-off. Otherwise: requires revision.

End your review with exactly these lines:
  Overall score: X/10
  Key issues: [bullet list]
  THREAT-MODEL FLAGS: [bullet list, or "None detected"]
  SBOM-GAP FLAGS: [bullet list, or "None detected"]
  PATCHABILITY FLAGS: [bullet list, or "None detected"]

REVIEW:
{output}
