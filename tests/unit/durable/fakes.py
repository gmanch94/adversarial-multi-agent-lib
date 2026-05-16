"""In-process fakes for durable workflow tests."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from adv_multi_agent.core.config import Config, ReviewerProvider
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


def make_test_config(tmp_path: Any) -> Config:
    return Config(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=3,
        score_threshold=7.5,
    )
