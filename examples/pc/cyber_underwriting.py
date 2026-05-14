"""
Cyber-underwriting example — runs CyberUnderwritingWorkflow on a synthetic
healthcare-software-vendor submission (200-employee SaaS company serving
US hospitals; HIPAA-regulated data; high-target industry).

Triple-flag gate (CONTROL-GAP / SUB-LIMIT / AGGREGATION); no veto.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.pc.cyber_underwriting
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.pc.workflows.cyber_underwriting import (
    CyberUnderwritingRequest,
    CyberUnderwritingWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = CyberUnderwritingRequest(
        applicant_summary=(
            "MedFlow Systems Inc. — healthcare-workflow SaaS for mid-market US "
            "hospitals (50–400-bed range). Revenue: $34M ARR (2025). Employees: 198. "
            "Data footprint: PHI for approximately 11.2M unique patients across 87 "
            "customer hospitals (HIPAA-regulated). Hosts production in AWS us-east-1 "
            "and us-west-2. No on-prem infrastructure."
        ),
        control_attestations=(
            "MFA: attested on all admin accounts and customer-facing portals. "
            "EDR: CrowdStrike Falcon on 100% of endpoints. "
            "Backups: AWS S3 with versioning + cross-region replication; restore tested "
            "quarterly. Immutability: attested but not via S3 Object Lock. "
            "Vendor management: SOC 2 reviews collected from top 12 vendors annually. "
            "Patching: critical patches within 14 days SLA. "
            "Training: phishing simulations quarterly; last failure rate 9%."
        ),
        control_evidence=(
            "Third-party scan (BitSight): score 720/950 (Advanced). Last incident: "
            "2024-09 — credential-stuffing campaign against customer portal; no PHI "
            "exfiltration; required customer-account password reset for ~3% of accounts. "
            "Notable gap: S3 Object Lock NOT configured on backup buckets (immutability "
            "is policy + IAM, not true write-once). No formal IR retainer in place — "
            "company relies on AWS Shield + internal incident response."
        ),
        requested_coverage=(
            "Aggregate $10M. Sub-limits requested: ransomware $7.5M; BI $5M (12-month); "
            "data restoration $2M; privacy/regulatory $5M; social engineering $500k; "
            "media $1M; system failure $2M. Retention $100k each-and-every. "
            "War / cyber-terrorism exclusion: LMA5564 wording requested by broker."
        ),
        proposed_terms=(
            "Premium: $148k. Retention: $100k. Aggregate: $10M. Ransomware sub-limit: "
            "$5M (reduced from $7.5M requested — Object Lock gap). Other sub-limits "
            "as requested. War / cyber-terrorism: LMA5564. "
            "Conditions precedent: IR retainer must be in place within 60 days of bind; "
            "S3 Object Lock on production backup buckets within 90 days."
        ),
        aggregation_context=(
            "Healthcare-SaaS portfolio concentration: currently 18% of LOB aggregate "
            "($90M of $500M cap); this bind would add 2%, reaching 20% (cap is 25%). "
            "AWS-hosted insureds: 41% of portfolio (cap is 50% per cloud provider). "
            "Common-vendor risk: 23 portfolio insureds use Snowflake; this applicant "
            "does not. CrowdStrike-dependent insureds: 67% of portfolio — material "
            "post-2024 outage exposure. No current high-severity unpatched CVE on "
            "applicant per BitSight scan."
        ),
    )

    workflow = CyberUnderwritingWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Applicant: {result.metadata['applicant_summary'][:80]}...")
    print()
    print(result.output)
    print()
    print("--- Approver Checklist ---")
    for item in result.metadata["approver_checklist"]:
        print(item)
    for label, key in [
        ("Control-Gap Flags", "control_gap_flags"),
        ("Sub-Limit Flags", "sub_limit_flags"),
        ("Aggregation Flags", "aggregation_flags"),
    ]:
        flags = result.metadata.get(key, [])
        if flags:
            print(f"\n--- {label} ---")
            for flag in flags:
                print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
