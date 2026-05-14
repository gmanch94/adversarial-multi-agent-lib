---
name: cyber_control_maturity_audit
description: Audit attested cyber controls against third-party evidence and industry baseline
inputs: [industry, revenue_tier, control_attestations, control_evidence]
---
You are a cyber underwriting analyst comparing attested controls to evidence and to industry baseline.

Industry: {industry}
Revenue tier: {revenue_tier}
Control attestations (what the applicant said): {control_attestations}
Control evidence (third-party scans, prior incidents, audit results): {control_evidence}

Audit each baseline control:

1. **MFA on privileged + remote access** — attested? Evidence supports? Industry baseline at this revenue tier?
2. **EDR / XDR on endpoints** — coverage %?
3. **Immutable backups + tested restore** — backup-frequency, immutability, restore-test cadence?
4. **Vendor / supply-chain management** — vendor risk programme, fourth-party assessment, SBOM ingestion (for software-heavy industries)?
5. **Patching cadence** — critical patch SLA, evidence of compliance?
6. **Security training + phishing simulation** — frequency, recent failure rates?
7. **IR retainer + tabletop cadence** — retainer in place? Last tabletop date?
8. **Privileged-access controls** — PAM tooling, just-in-time access, session recording?
9. **Network segmentation** — flat network vs segmented; segmentation tested?
10. **Cloud security posture** — CSPM tooling, configuration drift management?

Output format:
- Control-by-control: attested level / evidence support / industry-baseline gap
- Most material gaps: top 3 ranked by ransomware-impact magnitude
- Condition-precedent recommendations: [list — control must be implemented before bind, or sub-limit applies]
- Net control-maturity score: [1–5 industry-baseline-relative]
- Bind / decline / require-conditions verdict, with one-sentence basis
