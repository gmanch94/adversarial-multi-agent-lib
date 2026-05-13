"""
Example: run the Auto Review Loop on a short research abstract.

Run from the repo root (no sys.path hack needed since src/ is a regular package):

    cp .env.example .env          # fill in ANTHROPIC_API_KEY + OPENAI_API_KEY
    pip install -e .
    python -m examples.research.basic_review_loop

This walks an executor + cross-model reviewer through the convergence loop,
then prints the final output, ledger summary, and any pending self-improvement
proposals (which the caller — you — must explicitly approve via
`wiki.approve_improvement(id)`).
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, EffortLevel
from adv_multi_agent.research.workflows.review_loop import AutoReviewLoop


TASK = """\
Write a 300-word abstract for a research paper on the following topic:

"Adversarial multi-agent collaboration for scientific writing: using cross-model
reviewer pairing to reduce confirmation bias and improve manuscript quality."

The abstract should cover: motivation, method, key result, and conclusion.
Include specific (plausible) quantitative results.
"""


async def main() -> None:
    config = Config.from_env()
    config.effort = EffortLevel.HIGH
    config.max_review_rounds = 3
    config.score_threshold = 7.5

    workflow = AutoReviewLoop(config)

    print("Starting Auto Review Loop...")
    print(f"  executor : {config.executor_model}")
    print(f"  reviewer : {config.reviewer_model} ({config.reviewer_provider.value})")
    print(f"  rounds   : max {config.max_review_rounds}  |  threshold {config.score_threshold}")
    print()

    result = await workflow.run(
        task=TASK,
        criteria="clarity, scientific rigour, novelty claim strength, quantitative specificity",
    )

    print("=" * 60)
    print(
        f"Converged: {result.converged}  |  "
        f"Rounds: {result.rounds}  |  "
        f"Score: {result.final_score:.1f}/10"
    )
    print("=" * 60)
    print(result.output)
    print()
    print("Ledger:", result.metadata.get("ledger_summary"))
    pending_ids = result.metadata.get("pending_improvement_ids", [])
    if pending_ids:
        print(
            f"Pending self-improvement proposals ({len(pending_ids)}) — "
            "review via workflow.wiki.get(id) and approve/reject explicitly:"
        )
        for pid in pending_ids:
            entry = workflow.wiki.get(pid)
            print(f"  [{pid}] {entry.title}")


if __name__ == "__main__":
    asyncio.run(main())
