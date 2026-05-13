"""
Workflow 5 — Manuscript Assurance (ARIS §4.3).

Chains three stages:
  1. AutoReviewLoop     — adversarial generate/review loop
  2. ClaimVerifier      — 3-stage verification of extracted claims
  3. ScientificEditor   — 5-pass editing pipeline

The verifier and editor share the same executor/reviewer instances as the
loop. The ledger accumulates claims from the loop and is then verified;
the wiki state carries forward unchanged.

Security properties:
- Editor raises ValueError on input > _MAX_INPUT_CHARS. We truncate before
  handing off; truncation is flagged in metadata so callers can inspect it.
- round_num passed to verify() is loop_result.rounds — the semantic assurance
  pass marker, not an independent counter.
- Editor does not invalidate verification: claims are ledger records keyed by
  their own IDs, independent of prose references.
"""
from __future__ import annotations

from typing import Any

from ...core.agents import ExecutorAgent, ReviewerAgent
from ...core.config import Config
from ...core.ledger import ClaimLedger
from ...core.wiki import ResearchWiki
from ...core.workflow import BaseWorkflow, WorkflowResult
from ..assurance.editor import ScientificEditor
from ..assurance.verifier import ClaimVerifier, VerificationReport
from .review_loop import AutoReviewLoop

# Must match ScientificEditor._MAX_INPUT_CHARS — kept local so callers can
# truncate themselves if needed, without importing a private constant.
_EDITOR_MAX_CHARS = 200_000


class ManuscriptAssurance(BaseWorkflow):
    """
    Full manuscript assurance pipeline.

    Args:
        task:     The generation task for the AutoReviewLoop.
        criteria: Review criteria forwarded to ReviewerAgent.review().
        context:  Background context forwarded to the executor on round 1.

    Returns WorkflowResult where:
        output        — final edited text
        rounds        — number of review loop rounds
        final_score   — reviewer score from the last loop round
        converged     — whether the loop met the score threshold
        metadata      — nested dict with loop / verification / editing summaries
    """

    def __init__(
        self,
        config: Config,
        executor: ExecutorAgent | None = None,
        reviewer: ReviewerAgent | None = None,
        ledger: ClaimLedger | None = None,
        wiki: ResearchWiki | None = None,
        loop: AutoReviewLoop | None = None,
        verifier: ClaimVerifier | None = None,
        editor: ScientificEditor | None = None,
    ) -> None:
        super().__init__(config, executor=executor, reviewer=reviewer, ledger=ledger, wiki=wiki)
        self._loop = loop or AutoReviewLoop(
            config,
            executor=self.executor,
            reviewer=self.reviewer,
            ledger=self.ledger,
            wiki=self.wiki,
        )
        self._verifier = verifier or ClaimVerifier(
            config,
            self.ledger,
            executor=self.executor,
            reviewer=self.reviewer,
        )
        self._editor = editor or ScientificEditor(
            config,
            executor=self.executor,
            reviewer=self.reviewer,
        )

    async def run(  # type: ignore[override]
        self,
        task: str,
        criteria: str = "correctness, novelty, clarity, rigor",
        context: str = "",
        **_: Any,
    ) -> WorkflowResult:
        # Stage 1 — adversarial review loop
        loop_result = await self._loop.run(task=task, criteria=criteria, context=context)

        # Stage 2 — claim verification (round_num = loop rounds completed)
        verification = await self._verifier.verify(
            document_context=loop_result.output,
            round_num=loop_result.rounds,
        )

        # Stage 3 — scientific editing (truncate if needed; editor raises on oversize)
        editor_input = loop_result.output
        editor_input_truncated = len(editor_input) > _EDITOR_MAX_CHARS
        if editor_input_truncated:
            editor_input = editor_input[:_EDITOR_MAX_CHARS]

        editing = await self._editor.edit(editor_input)

        return WorkflowResult(
            output=editing.final,
            rounds=loop_result.rounds,
            final_score=loop_result.final_score,
            converged=loop_result.converged,
            metadata={
                "loop": loop_result.metadata,
                "pending_improvement_ids": loop_result.metadata.get("pending_improvement_ids", []),
                "verification": _verification_summary(verification),
                "editing": {
                    "introduced_errors": editing.introduced_errors,
                    "flags": editing.flags,
                    "readability_improved": editing.readability_improved,
                    "notes": editing.notes,
                },
                "editor_input_truncated": editor_input_truncated,
            },
        )


def _verification_summary(r: VerificationReport) -> dict[str, Any]:
    return {
        "total_claims": r.total_claims,
        "supported": r.supported,
        "disputed": r.disputed,
        "retracted": r.retracted,
        "pass_rate": r.pass_rate,
        "contradictions": r.contradictions,
    }
