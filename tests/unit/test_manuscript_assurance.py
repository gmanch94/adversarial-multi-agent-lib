"""Integration tests for ManuscriptAssurance — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from pytest import approx as pytest_approx

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.core.workflow import WorkflowResult
from adv_multi_agent.research.assurance.editor import EditingReport
from adv_multi_agent.research.assurance.verifier import VerificationReport
from adv_multi_agent.research.workflows.manuscript_assurance import ManuscriptAssurance, _EDITOR_MAX_CHARS

from .fakes import FakeEditor, FakeLoop, FakeVerifier


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


def make_loop_result(
    output: str = "final output",
    rounds: int = 2,
    score: float = 8.5,
    converged: bool = True,
    improvement_ids: list[str] | None = None,
) -> WorkflowResult:
    return WorkflowResult(
        output=output,
        rounds=rounds,
        final_score=score,
        converged=converged,
        metadata={
            "ledger_summary": {},
            "pending_improvement_ids": improvement_ids or [],
            "pending_improvements_count": len(improvement_ids or []),
        },
    )


def make_verification(
    total: int = 3,
    supported: int = 3,
    disputed: int = 0,
    retracted: int = 0,
) -> VerificationReport:
    return VerificationReport(
        total_claims=total,
        supported=supported,
        disputed=disputed,
        retracted=retracted,
    )


def make_editing(
    final: str = "edited output",
    errors: list[str] | None = None,
    flags: list[str] | None = None,
    improved: bool = True,
) -> EditingReport:
    return EditingReport(
        original="",
        final=final,
        introduced_errors=errors or [],
        flags=flags or [],
        readability_improved=improved,
    )


def make_assurance(
    config: Config,
    tmp_path: Path,
    loop_result: WorkflowResult,
    verification: VerificationReport,
    editing: EditingReport,
) -> ManuscriptAssurance:
    return ManuscriptAssurance(
        config=config,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        loop=FakeLoop(loop_result),
        verifier=FakeVerifier(verification),
        editor=FakeEditor(editing),
    )


# ---------------------------------------------------------------------------
# Chain integration
# ---------------------------------------------------------------------------


class TestChainIntegration:
    async def test_output_is_edited_text(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path)
        result = await make_assurance(
            cfg, tmp_path,
            make_loop_result(output="draft"),
            make_verification(),
            make_editing(final="polished"),
        ).run(task="Write something.")

        assert result.output == "polished"

    async def test_rounds_and_score_from_loop(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path)
        result = await make_assurance(
            cfg, tmp_path,
            make_loop_result(rounds=3, score=9.1, converged=True),
            make_verification(),
            make_editing(),
        ).run(task="Write.")

        assert result.rounds == 3
        assert result.final_score == 9.1
        assert result.converged is True

    async def test_converged_false_propagates(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path)
        result = await make_assurance(
            cfg, tmp_path,
            make_loop_result(converged=False),
            make_verification(),
            make_editing(),
        ).run(task="Write.")

        assert result.converged is False


# ---------------------------------------------------------------------------
# Metadata structure
# ---------------------------------------------------------------------------


class TestMetadata:
    async def test_verification_summary_in_metadata(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path)
        result = await make_assurance(
            cfg, tmp_path,
            make_loop_result(),
            make_verification(total=5, supported=4, disputed=1),
            make_editing(),
        ).run(task="Write.")

        v = result.metadata["verification"]
        assert v["total_claims"] == 5
        assert v["supported"] == 4
        assert v["disputed"] == 1
        assert v["pass_rate"] == pytest_approx(0.8)

    async def test_editing_summary_in_metadata(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path)
        errors = ["introduced passive voice"]
        flags = ["[MISMATCH: 10% vs 12%]"]
        result = await make_assurance(
            cfg, tmp_path,
            make_loop_result(),
            make_verification(),
            make_editing(errors=errors, flags=flags, improved=False),
        ).run(task="Write.")

        e = result.metadata["editing"]
        assert e["introduced_errors"] == errors
        assert e["flags"] == flags
        assert e["readability_improved"] is False

    async def test_pending_improvement_ids_forwarded(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path)
        result = await make_assurance(
            cfg, tmp_path,
            make_loop_result(improvement_ids=["imp-1", "imp-2"]),
            make_verification(),
            make_editing(),
        ).run(task="Write.")

        assert result.metadata["pending_improvement_ids"] == ["imp-1", "imp-2"]

    async def test_no_truncation_flag_for_normal_output(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path)
        result = await make_assurance(
            cfg, tmp_path,
            make_loop_result(output="short output"),
            make_verification(),
            make_editing(),
        ).run(task="Write.")

        assert result.metadata["editor_input_truncated"] is False


# ---------------------------------------------------------------------------
# Oversized output truncation
# ---------------------------------------------------------------------------


class TestTruncation:
    async def test_oversized_output_truncated_not_raised(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path)
        oversized = "x" * (_EDITOR_MAX_CHARS + 1000)
        result = await make_assurance(
            cfg, tmp_path,
            make_loop_result(output=oversized),
            make_verification(),
            make_editing(final="edited"),
        ).run(task="Write.")

        assert result.metadata["editor_input_truncated"] is True
        assert result.output == "edited"

    async def test_exact_max_not_truncated(self, tmp_path: Path) -> None:
        cfg = make_config(tmp_path)
        exact = "y" * _EDITOR_MAX_CHARS
        result = await make_assurance(
            cfg, tmp_path,
            make_loop_result(output=exact),
            make_verification(),
            make_editing(final="edited"),
        ).run(task="Write.")

        assert result.metadata["editor_input_truncated"] is False

