"""Regression tests for BaseWorkflow._register_claims claim parsing.

Covers:
- L4: line-anchored `## Claims` split — a commentary mention in prose
  cannot mis-anchor the parser to an earlier point in the output.
- L1: hard cap on claims-per-round bounds ledger growth from a
  pathological executor output dumping unbounded bullets.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.workflow import (
    BaseWorkflow,
    WorkflowResult,
    _MAX_CLAIMS_PER_ROUND,
)
from .fakes import FakeExecutor, FakeReviewer


class _NullWorkflow(BaseWorkflow):
    """Concrete BaseWorkflow stub — only `_register_claims` is exercised."""

    async def run(self, **kwargs: Any) -> WorkflowResult:  # pragma: no cover
        raise NotImplementedError


def _make_config(tmp_path: Path) -> Config:
    return Config(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=1,
        score_threshold=7.5,
    )


def _make_workflow(tmp_path: Path) -> _NullWorkflow:
    cfg = _make_config(tmp_path)
    return _NullWorkflow(
        config=cfg,
        executor=FakeExecutor(["ok"]),
        reviewer=FakeReviewer([]),
    )


class TestRegisterClaimsHeaderAnchoring:
    def test_commentary_mention_does_not_mis_anchor(self, tmp_path: Path) -> None:
        """L4 — a prose line that mentions `## Claims` inline must not be
        treated as the section start. The real section, marked with a
        line-anchored header, is what gets parsed.
        """
        wf = _make_workflow(tmp_path)
        output = (
            "Prefix prose with `## Claims` token inline only.\n"
            "- not a real claim, comes before header\n"
            "\n"
            "## Claims\n"
            "- real claim one\n"
            "- real claim two\n"
        )
        wf._register_claims(output, round_num=1)
        texts = [c.text for c in wf.ledger.all()]
        assert texts == ["real claim one", "real claim two"]

    def test_header_only_matches_at_line_start(self, tmp_path: Path) -> None:
        """If the section is never declared at line-start, no claims register."""
        wf = _make_workflow(tmp_path)
        output = "Inline reference to ## Claims only.\n- would-be claim"
        wf._register_claims(output, round_num=1)
        assert wf.ledger.all() == []

    def test_indented_header_is_not_a_section(self, tmp_path: Path) -> None:
        """`## Claims` must be at column 0 — indented (code-fence-like)
        mentions are not section headers."""
        wf = _make_workflow(tmp_path)
        output = "    ## Claims\n- nope"
        wf._register_claims(output, round_num=1)
        assert wf.ledger.all() == []


class TestRegisterClaimsCap:
    def test_caps_at_max_claims_per_round(self, tmp_path: Path) -> None:
        """L1 — pathological executor output emitting more than
        _MAX_CLAIMS_PER_ROUND bullets is truncated."""
        wf = _make_workflow(tmp_path)
        bullets = "\n".join(
            f"- claim {i}" for i in range(_MAX_CLAIMS_PER_ROUND + 75)
        )
        output = f"## Claims\n{bullets}"
        wf._register_claims(output, round_num=1)
        claims = wf.ledger.all()
        assert len(claims) == _MAX_CLAIMS_PER_ROUND
        # First N preserved in order.
        assert claims[0].text == "claim 0"
        assert claims[-1].text == f"claim {_MAX_CLAIMS_PER_ROUND - 1}"

    def test_duplicates_do_not_count_against_cap(self, tmp_path: Path) -> None:
        """Cap counts successful adds, not iterations — duplicates are
        skipped by the existing dedup and do not consume cap budget."""
        wf = _make_workflow(tmp_path)
        # 50 unique + 50 duplicates of the first = 50 added, well under cap.
        unique_bullets = "\n".join(f"- u{i}" for i in range(50))
        dup_bullets = "\n".join("- u0" for _ in range(50))
        output = f"## Claims\n{unique_bullets}\n{dup_bullets}"
        wf._register_claims(output, round_num=1)
        assert len(wf.ledger.all()) == 50
