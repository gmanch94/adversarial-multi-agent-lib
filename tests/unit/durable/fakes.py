"""In-process fakes for durable workflow tests."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.durable.workflow import PauseContext
from adv_multi_agent.core.workflow import BaseWorkflow, WorkflowResult


@dataclass
class ToyRequest:
    payload: str

    def to_prompt_text(self) -> str:
        return f"Task: {self.payload}"


class ToyConvergentWorkflow(BaseWorkflow):
    """Trivial workflow that returns a fixed output after one 'round'."""

    async def run(self, request: ToyRequest, **_: Any) -> WorkflowResult:  # type: ignore[override]
        return WorkflowResult(
            output=f"OK: {request.payload}",
            rounds=1,
            final_score=9.0,
            converged=True,
            metadata={"toy": True},
        )


@dataclass
class ToyPausingRequest:
    payload: str
    pause_on_round: int | None = None

    def to_prompt_text(self) -> str:
        return f"Task: {self.payload}"


class ToyPausingWorkflow(BaseWorkflow):
    """Workflow that pauses at a specified round via ctx.pause(). Used to
    validate the per-round orchestration + PauseContext."""

    async def run_round(  # type: ignore[override]
        self,
        round_num: int,
        request: "ToyPausingRequest",
        prior_state: dict | None,
        ctx: PauseContext | None = None,
    ) -> dict:
        if ctx is not None and request.pause_on_round == round_num:
            await ctx.pause(
                reason="toy_pause",
                context={"at_round": round_num},
                wake_at=None,
            )
        return {
            "output": f"OK: {request.payload} (round {round_num})",
            "score": 9.0,
            "converged": True,
            "rounds_history_entry": {"round": round_num, "score": 9.0},
        }

    async def run(self, request, **_):  # type: ignore[override]
        r = await self.run_round(1, request, prior_state=None, ctx=None)
        return WorkflowResult(
            output=r["output"], rounds=1, final_score=r["score"],
            converged=r["converged"], metadata={},
        )


def make_test_config(tmp_path: Any) -> Config:
    return Config(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=3,
        score_threshold=7.5,
    )
