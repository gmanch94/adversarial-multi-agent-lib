"""
Premarket Device Cybersecurity Review — worked example (no-veto path).

Synthetic scenario: a network-connected infusion pump (generic device CATEGORY —
no brand). The package below has a DELIBERATE SBOM gap — an embedded TLS library
carrying a known CVE is absent from the SBOM, and the pump firmware has no field-
update path between annual services — so the reviewer is expected to raise
SBOM-GAP and PATCHABILITY flags and the workflow should NOT converge on the first
round.

Illustrative FDA premarket cybersecurity references are scenario context, not
legal or regulatory advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/premarket_cybersecurity.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.premarket_cybersecurity import (
    PremarketCybersecurityRequest,
    PremarketCybersecurityWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/premarket-cyber-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = PremarketCybersecurityRequest(
        device_description=(
            "A network-connected large-volume infusion pump with 802.11 Wi-Fi, a "
            "USB service/maintenance port, BLE to a companion mobile app, and a "
            "wired hospital-network interface. Class II device."
        ),
        intended_use_environment=(
            "Deployed on the hospital biomedical VLAN; the companion app runs on "
            "clinician-owned mobile devices over the hospital wireless network."
        ),
        threat_model_summary=(
            "STRIDE analysis across the Wi-Fi, USB, BLE, and wired interfaces. "
            "Spoofing of the pump-to-app channel and tampering with firmware over "
            "the service port were identified as the two highest-risk threats."
        ),
        security_controls=(
            "TLS 1.2+ for all network traffic; cryptographically signed firmware "
            "verified at boot; role-based authentication on the service port; "
            "BLE pairing with out-of-band confirmation."
        ),
        sbom_summary=(
            # DELIBERATE gap: the embedded TLS library is not listed.
            "Components: a real-time operating system, a BLE protocol stack, and "
            "the drug-library engine. The mobile app uses a cross-platform UI "
            "framework. (No cryptographic-library entry is listed.)"
        ),
        vulnerability_assessment=(
            "Two medium-severity CVEs in the BLE stack were triaged and patched. "
            "The cryptographic library version is not stated, so its known "
            "vulnerabilities were not assessed."
        ),
        patchability_plan=(
            # DELIBERATE gap: firmware only updates at annual service.
            "The mobile app receives over-the-air updates through the app store. "
            "Pump firmware is updated only during the annual preventive-maintenance "
            "service visit."
        ),
        residual_risk_summary=(
            "After controls, residual cyber risk to essential performance "
            "(delivering the programmed dose) is rated low."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = PremarketCybersecurityWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running PremarketCybersecurityWorkflow...")
    print(f"Device: {request.device_description[:80]}...")
    print()

    result = await workflow.run(request=request)

    print("=" * 70)
    print(f"Rounds: {result.rounds}  |  Score: {result.final_score:.1f}  |  "
          f"Converged: {result.converged}")
    print()

    print("OUTPUT:")
    print(result.output)
    print()
    print("CYBERSECURITY CHECKLIST:")
    for item in result.metadata["cybersecurity_checklist"]:
        print(f"  {item}")
    print()

    tm = result.metadata["threat_model_flags"]
    sb = result.metadata["sbom_gap_flags"]
    pa = result.metadata["patchability_flags"]
    if tm or sb or pa:
        print(f"Threat-model flags ({len(tm)}): {tm}")
        print(f"SBOM-gap flags ({len(sb)}): {sb}")
        print(f"Patchability flags ({len(pa)}): {pa}")


if __name__ == "__main__":
    asyncio.run(main())
