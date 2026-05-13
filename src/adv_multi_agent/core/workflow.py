"""Base workflow contract."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .agents import ExecutorAgent, ReviewerAgent
from .config import Config
from .ledger import ClaimLedger
from .wiki import ResearchWiki


@dataclass
class WorkflowResult:
    output: str
    rounds: int
    final_score: float
    converged: bool
    metadata: dict[str, Any] = field(default_factory=dict)


class BaseWorkflow(ABC):
    def __init__(
        self,
        config: Config,
        executor: ExecutorAgent | None = None,
        reviewer: ReviewerAgent | None = None,
        ledger: ClaimLedger | None = None,
        wiki: ResearchWiki | None = None,
    ) -> None:
        self.config = config
        self.executor = executor or ExecutorAgent(config)
        self.reviewer = reviewer or ReviewerAgent(config)
        self.ledger = ledger or ClaimLedger(config.ledger_path)
        self.wiki = wiki or ResearchWiki(config.wiki_path)

    @abstractmethod
    async def run(self, **kwargs: Any) -> WorkflowResult: ...
