"""
Design Control Traceability Audit — worked example (no-veto path).

Synthetic scenario: a continuous glucose monitor (generic device CATEGORY — no
brand). The Design History File excerpt below carries one DELIBERATE orphan
design input (DI-04 biocompatible adhesive) with no linked design output, so the
reviewer is expected to raise a TRACE-GAP flag and the workflow should NOT
converge on the first round.

Illustrative 21 CFR 820.30 / ISO 13485 / ISO 14971 references are scenario
context, not legal or regulatory advice.

Run with:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python examples/lifesciences/design_control_traceability.py

Requires valid API keys. Generates live model calls.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.lifesciences.workflows.design_control_traceability import (
    DesignControlRequest,
    DesignControlTraceabilityWorkflow,
)


async def main() -> None:
    config = Config(
        anthropic_api_key=os.environ["ANTHROPIC_API_KEY"],
        openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
        reviewer_provider=ReviewerProvider.OPENAI,
        workspace_dir="/tmp/design-control-example",
        max_review_rounds=3,
        score_threshold=7.5,
    )

    # Continuous glucose monitor DHF excerpt. DI-04 is a DELIBERATE orphan input
    # (no linked design output) → reviewer should raise a TRACE-GAP flag.
    request = DesignControlRequest(
        device_description=(
            "Continuous glucose monitor (CGM): a single-use subcutaneous glucose "
            "sensor, a reusable transmitter, and a receiver/mobile app. Intended "
            "use: continuous interstitial glucose measurement in adults with "
            "diabetes over a 14-day wear period, with hypoglycemia/hyperglycemia "
            "alerts. Class II device."
        ),
        design_inputs=(
            "DI-01: Sensor accuracy MARD <= 10% across 40–400 mg/dL. "
            "DI-02: 14-day continuous sensor wear life. "
            "DI-03: Audible + haptic alert when interstitial glucose < 70 mg/dL. "
            "DI-04: Skin-contact adhesive is biocompatible per ISO 10993-10 for "
            "14-day prolonged contact. "
            "DI-05: Transmitter Bluetooth range >= 6 m line-of-sight to receiver."
        ),
        design_outputs=(
            "DO-01: Sensor electrode + membrane spec rev C (targets MARD <= 10%). "
            "DO-02: Transmitter firmware v2.1 (14-day session timer, BLE stack). "
            "DO-03: Alert-logic spec (threshold 70 mg/dL, audible + haptic). "
            "DO-05: BLE RF spec (>= 6 m range)."
            # NOTE: no DO maps to DI-04 (adhesive biocompatibility) — orphan input.
        ),
        verification_evidence=(
            "VER-01: Bench accuracy report R-2026-118 → DO-01 (MARD 8.7%). "
            "VER-02: Accelerated wear + real-time 14-day stability test → DO-02. "
            "VER-03: Alert-threshold unit-test log UT-441 → DO-03. "
            "VER-05: RF range test → DO-05 (7.2 m measured)."
        ),
        validation_evidence=(
            "VAL-01: 30-subject clinical use study CS-2026-07 — device meets "
            "intended use for adult glucose monitoring and alerting over 14 days; "
            "human-factors summative on alert perception passed."
        ),
        risk_analysis_reference=(
            "RMF-2026-014 (ISO 14971). Key hazards: H-03 missed hypoglycemia "
            "alert (risk control: redundant audible + haptic alert, confirmed by "
            "VER-03 + VAL-01); H-07 skin irritation from adhesive (risk control: "
            "biocompatible adhesive — confirming V&V not yet cited)."
        ),
        design_review_records=(
            "DR-1: Design inputs frozen 2026-01-20. "
            "DR-2: Design outputs approved 2026-03-14. "
            "DR-3: V&V review scheduled 2026-06-02 (open)."
        ),
        trace_matrix_summary=(
            "DI-01→DO-01→VER-01; DI-02→DO-02→VER-02; "
            "DI-03→DO-03→VER-03→VAL-01; DI-05→DO-05→VER-05. "
            "DI-04 has no linked design output (orphan input)."
        ),
    )

    executor = ExecutorAgent(config=config)
    reviewer = ReviewerAgent(config=config)
    ledger = ClaimLedger(f"{config.workspace_dir}/ledger.json")
    wiki = ResearchWiki(f"{config.workspace_dir}/wiki.json")

    workflow = DesignControlTraceabilityWorkflow(
        executor=executor,
        reviewer=reviewer,
        config=config,
        ledger=ledger,
        wiki=wiki,
    )

    print("Running DesignControlTraceabilityWorkflow...")
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
    print("DESIGN CONTROL CHECKLIST:")
    for item in result.metadata["design_control_checklist"]:
        print(f"  {item}")
    print()

    tg = result.metadata["trace_gap_flags"]
    ver = result.metadata["verification_flags"]
    val = result.metadata["validation_flags"]
    if tg or ver or val:
        print(f"Trace-gap flags ({len(tg)}): {tg}")
        print(f"Verification flags ({len(ver)}): {ver}")
        print(f"Validation flags ({len(val)}): {val}")


if __name__ == "__main__":
    asyncio.run(main())
