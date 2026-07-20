"""Unit tests for HEORDossierWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.heor_dossier import (
    HEORDossierRequest,
    HEORDossierWorkflow,
    _DISCLAIMER,
    _MAX_FIELD_CHARS,
)

from .fakes import FakeExecutor, FakeReviewer


def make_config(tmp_path: Path, **kwargs: Any) -> Config:
    defaults: dict[str, Any] = dict(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=3,
        score_threshold=7.5,
    )
    defaults.update(kwargs)
    return Config(**defaults)


def make_review(
    score: float,
    *,
    approved: bool,
    critique: str = "",
    suggestions: list[str] | None = None,
) -> ReviewResult:
    return ReviewResult(
        score=score,
        critique=critique,
        suggestions=suggestions or [],
        approved=approved,
    )


def make_request(**kwargs: Any) -> HEORDossierRequest:
    defaults: dict[str, Any] = dict(
        product_description="An oncology therapy for a solid-tumor indication.",
        value_proposition="Improved progression-free survival at an acceptable "
                         "cost per quality-adjusted life-year.",
        comparators="Compared against a chemotherapy regimen no longer first-line.",
        clinical_evidence_summary="A single pivotal trial with a PFS primary endpoint.",
        economic_model_summary="A lifetime partitioned-survival cost-effectiveness "
                              "model driven by PFS.",
        endpoints_used="Progression-free survival (surrogate); overall survival immature.",
        extrapolation_assumptions="Long-term survival extrapolated optimistically "
                                "from immature data.",
        target_audience="A national HTA body and hospital formulary committees.",
    )
    defaults.update(kwargs)
    return HEORDossierRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Value proposition:",
            "Comparators:",
            "Clinical evidence summary:",
            "Economic model summary:",
            "Endpoints used:",
            "Extrapolation assumptions:",
            "Target audience:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(comparators=oversized).to_prompt_text()
        section = text.split("Comparators:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Comparator appropriateness\nComparator fits"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="COMPARATOR FLAGS: None detected\n"
                         "ENDPOINT-RELEVANCE FLAGS: None detected\n"
                         "EXTRAPOLATION FLAGS: None detected",
            )
        ])
        wf = HEORDossierWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_comparator_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: wrong comparator\n"
            "COMPARATOR FLAGS:\n- The chosen comparator is no longer standard of care in the target market\n"
            "ENDPOINT-RELEVANCE FLAGS: None detected\n"
            "EXTRAPOLATION FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = HEORDossierWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["comparator_flags"] == [
            "The chosen comparator is no longer standard of care in the target market"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "COMPARATOR FLAGS:\n- Comparator outdated\n"
            "RECOMMENDATION: use current standard of care\n"
            "ENDPOINT-RELEVANCE FLAGS: None detected\n"
            "EXTRAPOLATION FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = HEORDossierWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.metadata["comparator_flags"] == ["Comparator outdated"]

    async def test_does_not_converge_when_extrapolation_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "COMPARATOR FLAGS: None detected\n"
            "ENDPOINT-RELEVANCE FLAGS: None detected\n"
            "EXTRAPOLATION FLAGS:\n- Long-term survival extrapolation not supported by the immature data\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = HEORDossierWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["extrapolation_flags"] == [
            "Long-term survival extrapolation not supported by the immature data"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="COMPARATOR FLAGS:\n- Comparator outdated\n"
                         "ENDPOINT-RELEVANCE FLAGS: None detected\n"
                         "EXTRAPOLATION FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="COMPARATOR FLAGS: None detected\n"
                         "ENDPOINT-RELEVANCE FLAGS: None detected\n"
                         "EXTRAPOLATION FLAGS: None detected",
            ),
        ])
        wf = HEORDossierWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_keys_and_checklist_owner(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="COMPARATOR FLAGS: None detected\n"
                         "ENDPOINT-RELEVANCE FLAGS: None detected\n"
                         "EXTRAPOLATION FLAGS: None detected",
            )
        ])
        wf = HEORDossierWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "comparator_flags",
            "endpoint_relevance_flags",
            "extrapolation_flags",
            "heor_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["heor_checklist"][0] == "[OWNER: HEOR / Market Access]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="COMPARATOR FLAGS: None detected\n"
                         "ENDPOINT-RELEVANCE FLAGS: None detected\n"
                         "EXTRAPOLATION FLAGS: None detected",
            )
        ])
        wf = HEORDossierWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
        assert "ADVISORY" in _DISCLAIMER.upper()


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        clean_critique = (
            "COMPARATOR FLAGS: None detected\n"
            "ENDPOINT-RELEVANCE FLAGS: None detected\n"
            "EXTRAPOLATION FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = HEORDossierWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
