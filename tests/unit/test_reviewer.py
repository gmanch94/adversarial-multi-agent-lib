"""Unit tests for ReviewerAgent.review() convergence gate (H2)."""
from __future__ import annotations

import pytest

from adv_multi_agent.core.agents import ReviewerAgent
from adv_multi_agent.core.config import Config, ReviewerProvider


class _StubReviewer(ReviewerAgent):
    """Skips backend init; lets us inject canned `run()` output."""

    def __init__(self, config: Config, canned: str) -> None:
        # bypass __init__ chain — we never call the backend
        self.config = config
        self._canned = canned

    async def run(self, prompt: str, context: str = "") -> str:  # type: ignore[override]
        return self._canned


def _config() -> Config:
    return Config(
        anthropic_api_key="test-key",
        openai_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir="./.tmp-test",
        score_threshold=8.0,
    )


@pytest.mark.asyncio
async def test_h2_high_score_no_critique_not_approved() -> None:
    """A reviewer emitting {"score":10} with no critique must NOT flip approved."""
    r = _StubReviewer(_config(), canned='{"score": 10}')
    result = await r.review("dummy content")
    assert result.score == 10.0
    assert result.approved is False


@pytest.mark.asyncio
async def test_h2_high_score_empty_critique_not_approved() -> None:
    r = _StubReviewer(_config(), canned='{"score": 9, "critique": ""}')
    result = await r.review("dummy content")
    assert result.approved is False


@pytest.mark.asyncio
async def test_h2_high_score_whitespace_critique_not_approved() -> None:
    r = _StubReviewer(_config(), canned='{"score": 9, "critique": "   \\n  "}')
    result = await r.review("dummy content")
    assert result.approved is False


@pytest.mark.asyncio
async def test_h2_high_score_short_critique_not_approved() -> None:
    # Under the 20-char minimum.
    r = _StubReviewer(_config(), canned='{"score": 9, "critique": "ok"}')
    result = await r.review("dummy content")
    assert result.approved is False


@pytest.mark.asyncio
async def test_h2_high_score_real_critique_approved() -> None:
    critique = "Methodology is sound and results align with hypothesis."
    r = _StubReviewer(_config(), canned=f'{{"score": 9, "critique": "{critique}"}}')
    result = await r.review("dummy content")
    assert result.approved is True
    assert result.critique == critique


@pytest.mark.asyncio
async def test_h2_low_score_with_critique_not_approved() -> None:
    r = _StubReviewer(
        _config(),
        canned='{"score": 5, "critique": "Several issues remain in the analysis."}',
    )
    result = await r.review("dummy content")
    assert result.approved is False
