"""
Recall scope example — runs RecallScopeWorkflow with a synthetic Listeria
contamination scenario.

This demonstrates the reviewer-veto pattern (D-RETAIL-1): the reviewer can
halt the workflow regardless of score if a safety-critical gap is detected.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.retail.recall_scope
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.retail.workflows.recall_scope import (
    RecallRequest,
    RecallScopeWorkflow,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = RecallRequest(
        contamination_signal=(
            "Supplier alert 2026-05-12 19:40 ET: Listeria monocytogenes positive on "
            "environmental swab from RTE chicken-salad production line 3 (collected "
            "2026-05-08, confirmed 2026-05-12). No finished-product positive yet; "
            "lab retest on hold lots in progress. Customer complaints: 0 to date."
        ),
        supplier_lot=(
            "LOT-CS-20260508-A (line 3, shift 1, 0600–1400 ET); "
            "LOT-CS-20260508-B (line 3, shift 2, 1400–2200 ET). "
            "Sibling lot LOT-CS-20260508-C (line 3, shift 3, 2200–0600 ET) NOT yet "
            "tested — same production day, same line."
        ),
        product_skus=(
            "SKU-RTE-CKN-001 (Kroger Brand 12oz Chicken Salad); "
            "SKU-RTE-CKN-002 (Kroger Brand 24oz Chicken Salad — family pack)"
        ),
        distribution_window=(
            "Production 2026-05-08; DC inbound 2026-05-08; "
            "DC-to-store ship dates 2026-05-09 through 2026-05-11. "
            "Best-by date 2026-05-22."
        ),
        stores_in_scope=(
            "KRO-OH-0042 (Columbus); KRO-OH-0043 (Westerville); "
            "KRO-KY-0118 (Florence); KRO-IN-0211 (Indianapolis); "
            "KRO-MI-0307 (Ann Arbor). Total 5 stores."
        ),
        consumer_exposure=(
            "Approx 1,840 units sold across the 5 stores between 2026-05-09 and "
            "2026-05-13. Loyalty-linked purchases: 612 (33% of units). "
            "Remaining at-shelf inventory: ~410 units."
        ),
        regulatory_context=(
            "FDA-regulated RTE meat product. 21 CFR Part 7 applies. "
            "Listeria-positive on RTE → Class I recall by default. "
            "State notifications required in OH, KY, IN, MI. "
            "Reportable Food Registry submission within 24 hours of confirmation."
        ),
        competing_evidence=(
            "Supplier disputes positive — claims swab was taken during a sanitation "
            "cycle and may reflect cleanup-chemical interference, not viable "
            "contamination. Lab retest pending (~36 hours). "
            "No clinical illness reports. "
            "Last positive on this line: 14 months ago (unrelated lot)."
        ),
    )

    workflow = RecallScopeWorkflow(config=config)
    result = await workflow.run(request=request)

    print(
        f"Converged: {result.converged} | Rounds: {result.rounds} | "
        f"Score: {result.final_score:.1f}/10"
    )
    print(f"Supplier lot(s): {result.metadata['supplier_lot']}")
    if result.metadata.get("vetoed"):
        print(f"\n🛑 VETO: {result.metadata['veto_reason']}")
    print()
    print(result.output)
    print()
    print("--- Safety Officer Checklist ---")
    for item in result.metadata["safety_checklist"]:
        print(item)
    if result.metadata["scope_flags"]:
        print("\n--- Scope Flags ---")
        for flag in result.metadata["scope_flags"]:
            print(f"  • {flag}")
    if result.metadata["evidence_flags"]:
        print("\n--- Evidence Flags ---")
        for flag in result.metadata["evidence_flags"]:
            print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
