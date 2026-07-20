"""Unit tests for REMSDesignWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.rems_design import (
    REMSDesignRequest,
    REMSDesignWorkflow,
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


def make_request(**kwargs: Any) -> REMSDesignRequest:
    defaults: dict[str, Any] = dict(
        product_description="A long-acting opioid analgesic with a serious risk "
                            "of addiction, misuse, and overdose.",
        serious_risks="Addiction, misuse, abuse; life-threatening respiratory "
                      "depression; accidental exposure/overdose.",
        rems_goals="Reduce the risk of overdose by informing prescribers and "
                   "patients about safe use, storage, and disposal.",
        rems_elements="Medication Guide; prescriber communication plan; "
                      "prescriber training element.",
        etasu_summary="Prescriber training on safe opioid prescribing; no "
                      "pharmacy certification proposed.",
        implementation_system="Training delivered via an accredited provider; "
                              "Med Guide dispensed at pharmacy.",
        assessment_plan="Survey prescriber knowledge at 12/24 months; count "
                        "trained prescribers.",
        burden_assessment="Training is a one-time online module; low burden on "
                          "prescribers and no access barrier for patients.",
    )
    defaults.update(kwargs)
    return REMSDesignRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Serious risks:",
            "REMS goals:",
            "REMS elements:",
            "ETASU summary:",
            "Implementation system:",
            "Assessment plan:",
            "Burden assessment:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(serious_risks=oversized).to_prompt_text()
        section = text.split("Serious risks:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Risk-to-element mapping\nEvery risk covered"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="RISK-MITIGATION FLAGS: None detected\n"
                         "BURDEN FLAGS: None detected\n"
                         "ASSESSMENT-PLAN FLAGS: None detected",
            )
        ])
        wf = REMSDesignWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_assessment_plan_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: assessment metric gap\n"
            "RISK-MITIGATION FLAGS: None detected\n"
            "BURDEN FLAGS: None detected\n"
            "ASSESSMENT-PLAN FLAGS:\n"
            "- No metric links REMS assessment to the reduction in the targeted overdose risk\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = REMSDesignWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["assessment_plan_flags"] == [
            "No metric links REMS assessment to the reduction in the targeted overdose risk"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "RISK-MITIGATION FLAGS:\n- Communication plan not tied to a serious risk\n"
            "RECOMMENDATION: re-map the elements\n"
            "BURDEN FLAGS: None detected\n"
            "ASSESSMENT-PLAN FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = REMSDesignWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.metadata["risk_mitigation_flags"] == [
            "Communication plan not tied to a serious risk"
        ]

    async def test_does_not_converge_when_burden_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "RISK-MITIGATION FLAGS: None detected\n"
            "BURDEN FLAGS:\n- Pharmacy certification imposes an access barrier beyond the risk\n"
            "ASSESSMENT-PLAN FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = REMSDesignWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["burden_flags"] == [
            "Pharmacy certification imposes an access barrier beyond the risk"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="RISK-MITIGATION FLAGS:\n- Element unmapped\n"
                         "BURDEN FLAGS: None detected\n"
                         "ASSESSMENT-PLAN FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="RISK-MITIGATION FLAGS: None detected\n"
                         "BURDEN FLAGS: None detected\n"
                         "ASSESSMENT-PLAN FLAGS: None detected",
            ),
        ])
        wf = REMSDesignWorkflow(executor=executor, reviewer=reviewer, config=config)
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
                critique="RISK-MITIGATION FLAGS: None detected\n"
                         "BURDEN FLAGS: None detected\n"
                         "ASSESSMENT-PLAN FLAGS: None detected",
            )
        ])
        wf = REMSDesignWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "risk_mitigation_flags",
            "burden_flags",
            "assessment_plan_flags",
            "rems_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["rems_checklist"][0] == "[OWNER: REMS / Risk Management Lead]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="RISK-MITIGATION FLAGS: None detected\n"
                         "BURDEN FLAGS: None detected\n"
                         "ASSESSMENT-PLAN FLAGS: None detected",
            )
        ])
        wf = REMSDesignWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
        assert "ADVISORY" in _DISCLAIMER.upper()


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        clean_critique = (
            "RISK-MITIGATION FLAGS: None detected\n"
            "BURDEN FLAGS: None detected\n"
            "ASSESSMENT-PLAN FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = REMSDesignWorkflow(executor=executor, reviewer=reviewer, config=config)
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
