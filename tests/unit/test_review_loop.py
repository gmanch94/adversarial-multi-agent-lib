"""Integration tests for AutoReviewLoop — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any


from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.workflows.review_loop import AutoReviewLoop

from .fakes import FakeExecutor, FakeReviewer


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_config(tmp_path: Path, **kwargs: Any) -> Config:
    defaults: dict[str, Any] = dict(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=3,
        score_threshold=8.0,
    )
    defaults.update(kwargs)
    return Config(**defaults)


def make_result(score: float, *, approved: bool, critique: str = "") -> ReviewResult:
    return ReviewResult(score=score, critique=critique, suggestions=[], approved=approved)


def make_loop(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
    ledger: ClaimLedger | None = None,
    wiki: ResearchWiki | None = None,
) -> AutoReviewLoop:
    return AutoReviewLoop(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ledger or ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=wiki or ResearchWiki(str(tmp_path / "wiki.json")),
    )


# ---------------------------------------------------------------------------
# Convergence
# ---------------------------------------------------------------------------


class TestConvergence:
    async def test_happy_path_converges_round_3(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, max_review_rounds=3, score_threshold=9.0)
        executor = FakeExecutor(["output1", "output2", "output3"])
        reviewer = FakeReviewer([
            make_result(5.0, approved=False),
            make_result(7.0, approved=False),
            make_result(9.5, approved=True),
        ])
        result = await make_loop(cfg, tmp_path, executor, reviewer).run(task="Write something.")

        assert result.converged is True
        assert result.rounds == 3
        assert result.final_score == 9.5

    async def test_converges_round_1(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, max_review_rounds=5, score_threshold=8.0)
        executor = FakeExecutor(["great output"])
        reviewer = FakeReviewer([make_result(10.0, approved=True)])
        result = await make_loop(cfg, tmp_path, executor, reviewer).run(task="Do something.")

        assert result.converged is True
        assert result.rounds == 1
        assert len(executor.prompts) == 1

    async def test_never_converges_exhausts_rounds(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, max_review_rounds=3, score_threshold=9.0)
        executor = FakeExecutor(["r1", "r2", "r3"])
        reviewer = FakeReviewer([
            make_result(5.0, approved=False),
            make_result(6.0, approved=False),
            make_result(7.0, approved=False),
        ])
        result = await make_loop(cfg, tmp_path, executor, reviewer).run(task="Try.")

        assert result.converged is False
        assert result.rounds == 3

    async def test_max_rounds_one_boundary(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, max_review_rounds=1, score_threshold=9.0)
        executor = FakeExecutor(["single"])
        reviewer = FakeReviewer([make_result(5.0, approved=False)])
        result = await make_loop(cfg, tmp_path, executor, reviewer).run(task="Once.")

        assert result.converged is False
        assert result.rounds == 1


# ---------------------------------------------------------------------------
# Prompt construction
# ---------------------------------------------------------------------------


class TestPromptConstruction:
    async def test_revision_prompt_used_from_round_2(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, max_review_rounds=2, score_threshold=9.0)
        executor = FakeExecutor(["first", "second"])
        reviewer = FakeReviewer([
            make_result(5.0, critique="needs work", approved=False),
            make_result(9.5, approved=True),
        ])
        await make_loop(cfg, tmp_path, executor, reviewer).run(task="Write.")

        assert "Reviewer critique" not in executor.prompts[0]
        assert "Reviewer critique" in executor.prompts[1]


# ---------------------------------------------------------------------------
# Self-improvement proposals — CRIT-2 regression guard
# ---------------------------------------------------------------------------


class TestSelfImprovementCrit2:
    async def test_improvement_stored_never_auto_approved(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, max_review_rounds=1, score_threshold=9.0)
        output = "Content.\n\n## Self-Improvement Proposals\nImprove the prompts."
        executor = FakeExecutor([output])
        reviewer = FakeReviewer([make_result(5.0, approved=False)])
        wiki = ResearchWiki(str(tmp_path / "wiki.json"))
        loop = make_loop(cfg, tmp_path, executor, reviewer, wiki=wiki)

        result = await loop.run(task="Do.")

        assert len(result.metadata["pending_improvement_ids"]) >= 1
        assert result.metadata["pending_improvements_count"] >= 1
        assert wiki.approved_improvements() == []


# ---------------------------------------------------------------------------
# Claim extraction
# ---------------------------------------------------------------------------


class TestClaimExtraction:
    async def test_claims_added_to_ledger(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, max_review_rounds=1, score_threshold=9.0)
        output = "Text.\n\n## Claims\n- The sky is blue.\n- Water is wet."
        executor = FakeExecutor([output])
        reviewer = FakeReviewer([make_result(5.0, approved=False)])
        ledger = ClaimLedger(str(tmp_path / "ledger.json"))
        loop = make_loop(cfg, tmp_path, executor, reviewer, ledger=ledger)

        await loop.run(task="Write.")

        claims = ledger.all()
        assert len(claims) == 2
        assert all(c.round_added == 1 for c in claims)

    async def test_duplicate_claim_not_re_added(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, max_review_rounds=2, score_threshold=9.0)
        same_output = "Text.\n\n## Claims\n- Duplicate claim."
        executor = FakeExecutor([same_output, same_output])
        reviewer = FakeReviewer([
            make_result(5.0, approved=False),
            make_result(5.0, approved=False),
        ])
        ledger = ClaimLedger(str(tmp_path / "ledger.json"))
        loop = make_loop(cfg, tmp_path, executor, reviewer, ledger=ledger)

        await loop.run(task="Write.")

        assert len(ledger.all()) == 1

    async def test_no_claims_section_no_crash(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, max_review_rounds=1, score_threshold=9.0)
        executor = FakeExecutor(["Just regular text with no claims section."])
        reviewer = FakeReviewer([make_result(5.0, approved=False)])
        ledger = ClaimLedger(str(tmp_path / "ledger.json"))
        loop = make_loop(cfg, tmp_path, executor, reviewer, ledger=ledger)

        await loop.run(task="Write.")

        assert ledger.all() == []

    async def test_oversized_claim_truncated_not_skipped(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path, max_review_rounds=1, score_threshold=9.0,
                          max_claim_text_chars=50)
        output = "Text.\n\n## Claims\n- " + "x" * 200
        executor = FakeExecutor([output])
        reviewer = FakeReviewer([make_result(5.0, approved=False)])
        ledger = ClaimLedger(str(tmp_path / "ledger.json"))
        loop = make_loop(cfg, tmp_path, executor, reviewer, ledger=ledger)

        await loop.run(task="Write.")

        claims = ledger.all()
        assert len(claims) == 1
        assert len(claims[0].text) == 50
