"""
Example: full Manuscript Assurance pipeline on a short research draft.

Run from the repo root:

    cp .env.example .env          # fill in ANTHROPIC_API_KEY + OPENAI_API_KEY
    pip install -e .
    python -m examples.manuscript_assurance

Chains three stages:
  1. AutoReviewLoop     — adversarial generate/review (up to 3 rounds)
  2. ClaimVerifier      — 3-stage claim verification on the ledger
  3. ScientificEditor   — 5-pass prose editing

Pending self-improvement proposals are surfaced in the output but never
auto-approved; call `workflow.wiki.approve_improvement(id)` explicitly after
human review.
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, EffortLevel
from adv_multi_agent.research.workflows.manuscript_assurance import ManuscriptAssurance


TASK = """\
Write a 400-word methods section for a research paper on the following topic:

"Adversarial multi-agent collaboration for scientific writing: using cross-model
reviewer pairing to reduce confirmation bias and improve manuscript quality."

The methods section should cover: experimental design, participant/dataset
details, evaluation metrics, and statistical analysis approach.
Include specific (plausible) quantitative details.
"""


async def main() -> None:
    config = Config.from_env()
    config.effort = EffortLevel.HIGH
    config.max_review_rounds = 3
    config.score_threshold = 7.5

    workflow = ManuscriptAssurance(config)

    print("Starting Manuscript Assurance pipeline...")
    print(f"  executor : {config.executor_model}")
    print(f"  reviewer : {config.reviewer_model} ({config.reviewer_provider.value})")
    print(f"  rounds   : max {config.max_review_rounds}  |  threshold {config.score_threshold}")
    print()

    result = await workflow.run(
        task=TASK,
        criteria="clarity, scientific rigour, methodological completeness, quantitative specificity",
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

    v = result.metadata["verification"]
    print(
        f"Claims: {v['total_claims']} total  |  "
        f"{v['supported']} supported  |  "
        f"{v['disputed']} disputed  |  "
        f"{v['retracted']} retracted  |  "
        f"pass rate {v['pass_rate']:.0%}"
    )
    if v["contradictions"]:
        print(f"Contradictions found: {len(v['contradictions'])}")
        for c in v["contradictions"]:
            print(f"  [{c.get('claim_a')} vs {c.get('claim_b')}] {c.get('reason')}")

    e = result.metadata["editing"]
    if e["introduced_errors"]:
        print("Introduced errors flagged by reviewer:")
        for err in e["introduced_errors"]:
            print(f"  - {err}")
    if e["flags"]:
        print("Flags needing attention:")
        for flag in e["flags"]:
            print(f"  - {flag}")

    if result.metadata.get("editor_input_truncated"):
        print("WARNING: loop output was truncated before editing (exceeded 200K chars)")

    pending_ids = result.metadata.get("pending_improvement_ids", [])
    if pending_ids:
        print(
            f"\nPending self-improvement proposals ({len(pending_ids)}) — "
            "review via workflow.wiki.get(id) and approve/reject explicitly:"
        )
        for pid in pending_ids:
            entry = workflow.wiki.get(pid)
            print(f"  [{pid}] {entry.title}")


if __name__ == "__main__":
    asyncio.run(main())
