"""Unit tests for PremarketCybersecurityWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.premarket_cybersecurity import (
    PremarketCybersecurityRequest,
    PremarketCybersecurityWorkflow,
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


def make_request(**kwargs: Any) -> PremarketCybersecurityRequest:
    defaults: dict[str, Any] = dict(
        device_description="A network-connected infusion pump with Wi-Fi, USB "
                           "service port, and a companion mobile app.",
        intended_use_environment="Hospital clinical network and, for the app, a "
                                 "clinician's mobile device.",
        threat_model_summary="STRIDE analysis of the Wi-Fi, USB, and BLE "
                             "interfaces; spoofing and tampering considered.",
        security_controls="TLS for network traffic; signed firmware; role-based "
                          "authentication on the service port.",
        sbom_summary="RTOS, BLE stack, and an embedded TLS library; app uses a "
                     "cross-platform framework.",
        vulnerability_assessment="Two medium CVEs in the BLE stack triaged; TLS "
                                "library version not stated.",
        patchability_plan="Over-the-air updates for the mobile app; pump firmware "
                          "updated only at annual service.",
        residual_risk_summary="Residual risk to essential performance rated low "
                             "after controls.",
    )
    defaults.update(kwargs)
    return PremarketCybersecurityRequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Device description:",
            "Intended use environment:",
            "Threat model summary:",
            "Security controls:",
            "SBOM summary:",
            "Vulnerability assessment:",
            "Patchability plan:",
            "Residual risk summary:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(sbom_summary=oversized).to_prompt_text()
        section = text.split("SBOM summary:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Threat-model coverage\nAll surfaces controlled"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="THREAT-MODEL FLAGS: None detected\n"
                         "SBOM-GAP FLAGS: None detected\n"
                         "PATCHABILITY FLAGS: None detected",
            )
        ])
        wf = PremarketCybersecurityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_sbom_gap_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: SBOM gap\n"
            "THREAT-MODEL FLAGS: None detected\n"
            "SBOM-GAP FLAGS:\n- Embedded TLS library with a known CVE is absent from the SBOM\n"
            "PATCHABILITY FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = PremarketCybersecurityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["sbom_gap_flags"] == [
            "Embedded TLS library with a known CVE is absent from the SBOM"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "THREAT-MODEL FLAGS:\n- USB service port has no authentication control\n"
            "RECOMMENDATION: add port authentication\n"
            "SBOM-GAP FLAGS: None detected\n"
            "PATCHABILITY FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = PremarketCybersecurityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.metadata["threat_model_flags"] == [
            "USB service port has no authentication control"
        ]

    async def test_does_not_converge_when_patchability_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "THREAT-MODEL FLAGS: None detected\n"
            "SBOM-GAP FLAGS: None detected\n"
            "PATCHABILITY FLAGS:\n- Pump firmware has no field-update path between annual services\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = PremarketCybersecurityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["patchability_flags"] == [
            "Pump firmware has no field-update path between annual services"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="THREAT-MODEL FLAGS:\n- USB port unauthenticated\n"
                         "SBOM-GAP FLAGS: None detected\n"
                         "PATCHABILITY FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="THREAT-MODEL FLAGS: None detected\n"
                         "SBOM-GAP FLAGS: None detected\n"
                         "PATCHABILITY FLAGS: None detected",
            ),
        ])
        wf = PremarketCybersecurityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
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
                critique="THREAT-MODEL FLAGS: None detected\n"
                         "SBOM-GAP FLAGS: None detected\n"
                         "PATCHABILITY FLAGS: None detected",
            )
        ])
        wf = PremarketCybersecurityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        for key in (
            "device_description",
            "threat_model_flags",
            "sbom_gap_flags",
            "patchability_flags",
            "cybersecurity_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["cybersecurity_checklist"][0] == (
            "[OWNER: Product Security / Regulatory]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="THREAT-MODEL FLAGS: None detected\n"
                         "SBOM-GAP FLAGS: None detected\n"
                         "PATCHABILITY FLAGS: None detected",
            )
        ])
        wf = PremarketCybersecurityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
        assert "ADVISORY" in _DISCLAIMER.upper()


@pytest.mark.asyncio
class TestScoreThresholdBoundary:
    async def test_does_not_converge_when_below_threshold(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["d1", "d2", "d3"])
        clean_critique = (
            "THREAT-MODEL FLAGS: None detected\n"
            "SBOM-GAP FLAGS: None detected\n"
            "PATCHABILITY FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = PremarketCybersecurityWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
