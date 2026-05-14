"""Base workflow contract."""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

from .agents import ExecutorAgent, ReviewerAgent
from .config import Config
from .ledger import ClaimLedger
from .wiki import ResearchWiki

# L1: hard cap on claims parsed per round. Bounds ledger growth from a
# pathological executor output dumping unbounded bullets under ## Claims.
# L4: line-anchor the section split so a commentary mention of "## Claims"
# in prose cannot mis-anchor the parser to an earlier point.
_MAX_CLAIMS_PER_ROUND = 200
_CLAIMS_HEADER_RE = re.compile(r"(?m)^##\s+Claims\s*$")


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

    def _register_claims(self, output: str, round_num: int) -> None:
        """
        Extract `## Claims` bullets from `output` and add each to `self.ledger`.

        Skips: empty lines, duplicates (against current ledger snapshot),
        and any claim that fails `ClaimLedger.add` validation (length cap,
        etc. — `ValueError` is swallowed by design: malformed claims do
        not halt the workflow). Per-claim text is truncated at
        `Config.max_claim_text_chars` (default 1000).

        Shared by retail workflows (demand_forecasting, labor_scheduling,
        recall_scope, loyalty_offer, promo_markdown). Subclasses can
        override if they need a different parse rule.
        """
        match = _CLAIMS_HEADER_RE.search(output)
        if match is None:
            return
        max_chars = getattr(self.config, "max_claim_text_chars", 1000)
        claims_section = output[match.end():]
        existing = {c.text for c in self.ledger.all()}
        added = 0
        for raw_line in claims_section.splitlines():
            if added >= _MAX_CLAIMS_PER_ROUND:
                break
            line = raw_line.strip().lstrip("-•").strip()
            if not line:
                continue
            if len(line) > max_chars:
                line = line[:max_chars]
            if line in existing:
                continue
            try:
                self.ledger.add(line, round_num=round_num)
                existing.add(line)
                added += 1
            except ValueError:
                continue
