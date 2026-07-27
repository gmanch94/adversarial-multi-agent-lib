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

import pytest

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
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


def _make_config(tmp_path: Path, *, max_claim_text_chars: int = 1000) -> Config:
    return Config(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=1,
        score_threshold=7.5,
        max_claim_text_chars=max_claim_text_chars,
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


class TestRegisterClaimsLengthBound:
    """A11-L6 — the default ledger's claim-text cap must track
    `Config.max_claim_text_chars`, and a dropped claim must never be silent."""

    def test_claim_within_config_cap_survives_default_ledger(
        self, tmp_path: Path
    ) -> None:
        """With `max_claim_text_chars` raised above the ledger's old 2000
        default, a long-but-in-bounds claim must land. Before the fix the
        default ledger kept its 2000 cap, so `ClaimLedger.add` raised on the
        longer claim and it was silently dropped from the audit trail."""
        cfg = _make_config(tmp_path, max_claim_text_chars=5000)
        wf = _NullWorkflow(
            config=cfg,
            executor=FakeExecutor(["ok"]),
            reviewer=FakeReviewer([]),
        )
        long_claim = "L" * 3000  # > old 2000 ledger default, < 5000 config cap
        output = f"## Claims\n- short one\n- {long_claim}\n"
        wf._register_claims(output, round_num=1)
        assert [c.text for c in wf.ledger.all()] == ["short one", long_claim]

    def test_drop_on_injected_smaller_ledger_is_warned_not_silent(
        self, tmp_path: Path
    ) -> None:
        """A caller that injects a ledger with a smaller bound than
        `max_claim_text_chars` still drops the over-bound claim — but the drop
        is surfaced as a warning carrying only the length (no claim text, so
        PHI-safe), never silently swallowed."""
        cfg = _make_config(tmp_path, max_claim_text_chars=5000)
        small_ledger = ClaimLedger(
            str(tmp_path / "ledger.json"), max_claim_chars=100
        )
        wf = _NullWorkflow(
            config=cfg,
            executor=FakeExecutor(["ok"]),
            reviewer=FakeReviewer([]),
            ledger=small_ledger,
        )
        payload = "X" * 500  # <= config cap (kept by truncation), > ledger 100
        output = f"## Claims\n- {payload}\n"
        with pytest.warns(UserWarning) as record:
            wf._register_claims(output, round_num=1)
        assert wf.ledger.all() == []
        assert len(record) == 1
        message = str(record[0].message)
        assert "dropped from the audit trail" in message
        assert payload not in message  # PHI-safe: no claim text in the warning
