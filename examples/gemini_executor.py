"""
Example: Gemini 2.5 Pro executor + GPT-4o reviewer (cross-provider adversarial loop).

Demonstrates:
  - ExecutorProvider.GEMINI routing to _GeminiExecutor (google-genai SDK)
  - ReviewerProvider.OPENAI as the cross-family adversarial reviewer
  - EffortLevel → Gemini thinking_budget mapping (HIGH = 8192 tokens)
  - Streaming output from the Gemini executor
  - Same converge/ledger/wiki result object as the Anthropic executor

Prerequisites:
    pip install -e ".[dev,gemini]"
    cp .env.example .env
    # Add to .env:
    #   GEMINI_API_KEY=<your-google-ai-studio-key>   (console.cloud.google.com)
    #   OPENAI_API_KEY=<your-openai-key>
    # ANTHROPIC_API_KEY is not required for this configuration.

Run:
    python -m examples.gemini_executor
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, EffortLevel, ExecutorProvider, ReviewerProvider
from adv_multi_agent.core.agents import ExecutorAgent
from adv_multi_agent.workflows.review_loop import AutoReviewLoop

TASK = """\
Write a 300-word abstract for a research paper on the following topic:
"Adversarial multi-agent collaboration for scientific writing: using cross-model
reviewer pairing to reduce confirmation bias and improve manuscript quality."
The abstract should cover: motivation, method, key result, and conclusion.
Include specific (plausible) quantitative results.
"""

_EFFORT_BUDGET_MAP = {
    EffortLevel.LOW: 0,
    EffortLevel.MEDIUM: 4096,
    EffortLevel.HIGH: 8192,
    EffortLevel.XHIGH: 16384,
}


async def demo_streaming(config: Config) -> None:
    """Stream a single Gemini executor response to stdout."""
    print("── Streaming demo (single Gemini call) ──")
    executor = ExecutorAgent(config)
    prompt = "In two sentences, explain why cross-family model pairing reduces echo-chamber bias."
    print(f"Prompt: {prompt}\n")
    print("Response: ", end="", flush=True)
    async for chunk in executor.stream(prompt):
        print(chunk, end="", flush=True)
    print("\n")


async def main() -> None:
    config = Config(
        executor_provider=ExecutorProvider.GEMINI,
        reviewer_provider=ReviewerProvider.OPENAI,
        effort=EffortLevel.HIGH,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    thinking_budget = _EFFORT_BUDGET_MAP[config.effort]

    print("Gemini executor + GPT-4o reviewer (cross-family adversarial loop)")
    print(f"  executor : {config.gemini_executor_model}  [thinking_budget={thinking_budget}]")
    print(f"  reviewer : {config.reviewer_model} ({config.reviewer_provider.value})")
    print(f"  rounds   : max {config.max_review_rounds}  |  threshold {config.score_threshold}")
    print()

    # --- streaming demo ---
    await demo_streaming(config)

    # --- full review loop ---
    print("── Auto Review Loop ──")
    workflow = AutoReviewLoop(config)
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
            f"\nPending self-improvement proposals ({len(pending_ids)}) — "
            "review and approve explicitly via workflow.wiki.approve_improvement(id):"
        )
        for pid in pending_ids:
            entry = workflow.wiki.get(pid)
            print(f"  [{pid}] {entry.title}")


if __name__ == "__main__":
    asyncio.run(main())
