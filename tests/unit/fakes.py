"""Fake agents and workflows for integration tests — no API calls."""
from __future__ import annotations

from typing import Any

from adv_multi_agent.core.agents import ExecutorAgent, ReviewerAgent, ReviewResult
from adv_multi_agent.core.workflow import WorkflowResult
from adv_multi_agent.research.assurance.editor import EditingReport, ScientificEditor
from adv_multi_agent.research.assurance.verifier import ClaimVerifier, VerificationReport
from adv_multi_agent.research.workflows.review_loop import AutoReviewLoop


class FakeExecutor(ExecutorAgent):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.prompts: list[str] = []

    async def run(self, prompt: str, context: str = "") -> str:
        self.prompts.append(prompt)
        return self._responses.pop(0) if self._responses else ""


class FakeReviewer(ReviewerAgent):
    def __init__(self, results: list[ReviewResult]) -> None:
        self._results = list(results)
        self.calls: list[str] = []

    async def review(self, content: str, criteria: str = "") -> ReviewResult:
        self.calls.append(content)
        return self._results.pop(0)

    async def run(self, prompt: str, context: str = "") -> str:
        return ""


class FakeLoop(AutoReviewLoop):
    """Returns a pre-built WorkflowResult; skips all agent calls."""

    def __init__(self, result: WorkflowResult) -> None:
        self._result = result

    async def run(  # type: ignore[override]
        self,
        task: str = "",
        criteria: str = "",
        context: str = "",
        **_: Any,
    ) -> WorkflowResult:
        return self._result


class FakeVerifier(ClaimVerifier):
    """Returns a pre-built VerificationReport; skips all agent calls."""

    def __init__(self, report: VerificationReport) -> None:
        self._report = report

    async def verify(self, document_context: str = "", round_num: int = 0) -> VerificationReport:
        return self._report


class FakeEditor(ScientificEditor):
    """Returns a pre-built EditingReport; skips all agent calls."""

    def __init__(self, report: EditingReport) -> None:
        self._report = report

    async def edit(self, text: str) -> EditingReport:
        return self._report
