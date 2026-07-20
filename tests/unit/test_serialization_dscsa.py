"""Unit tests for SerializationDSCSAWorkflow — no live API calls."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.lifesciences.workflows.serialization_dscsa import (
    SerializationDSCSARequest,
    SerializationDSCSAWorkflow,
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


def make_request(**kwargs: Any) -> SerializationDSCSARequest:
    defaults: dict[str, Any] = dict(
        product_description="An oral solid-dose prescription product in bottles, "
                           "cases, and pallets.",
        serialization_scheme="GTIN + serial + lot + expiry in a 2D DataMatrix on "
                            "each saleable unit.",
        aggregation_summary="Case-to-pallet aggregation captured; item-to-case "
                          "aggregation missing for a repackaged lot.",
        epcis_events="Commissioning, packing, and shipping events captured at the "
                    "line.",
        trading_partner_exchange="EPCIS 1.2 documents exchanged with authorized "
                               "trading partners.",
        verification_process="Product-identifier verification available for "
                           "suspect product.",
        saleable_returns_process="Returns verified at the lot level before resale.",
        interoperability_status="Working toward enhanced unit-level traceability.",
    )
    defaults.update(kwargs)
    return SerializationDSCSARequest(**defaults)


class TestRequestToPromptText:
    def test_renders_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product description:",
            "Serialization scheme:",
            "Aggregation summary:",
            "EPCIS events:",
            "Trading partner exchange:",
            "Verification process:",
            "Saleable returns process:",
            "Interoperability status:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(aggregation_summary=oversized).to_prompt_text()
        section = text.split("Aggregation summary:")[1].split("\n")[0]
        assert len(section.strip()) == _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["## Aggregation integrity\nAll links intact"])
        reviewer = FakeReviewer([
            make_review(
                8.5,
                approved=True,
                critique="AGGREGATION FLAGS: None detected\n"
                         "TRACEABILITY FLAGS: None detected\n"
                         "SALEABLE-RETURN FLAGS: None detected",
            )
        ])
        wf = SerializationDSCSAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert _DISCLAIMER in result.output

    async def test_does_not_converge_when_aggregation_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "Key issues: broken aggregation\n"
            "AGGREGATION FLAGS:\n- Item-to-case aggregation links are missing for the repackaged lot\n"
            "TRACEABILITY FLAGS: None detected\n"
            "SALEABLE-RETURN FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = SerializationDSCSAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["aggregation_flags"] == [
            "Item-to-case aggregation links are missing for the repackaged lot"
        ]

    async def test_stops_at_sibling_header(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "Overall score: 7.0/10\n"
            "AGGREGATION FLAGS:\n- Missing item-to-case link\n"
            "RECOMMENDATION: re-aggregate the repackaged lot\n"
            "TRACEABILITY FLAGS: None detected\n"
            "SALEABLE-RETURN FLAGS: None detected\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = SerializationDSCSAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.metadata["aggregation_flags"] == ["Missing item-to-case link"]

    async def test_does_not_converge_when_saleable_return_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, max_review_rounds=1)
        executor = FakeExecutor(["draft 1"])
        critique = (
            "AGGREGATION FLAGS: None detected\n"
            "TRACEABILITY FLAGS: None detected\n"
            "SALEABLE-RETURN FLAGS:\n- Saleable return verified at lot level only, not the unit serial\n"
        )
        reviewer = FakeReviewer([make_review(9.0, approved=True, critique=critique)])
        wf = SerializationDSCSAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.metadata["saleable_return_flags"] == [
            "Saleable return verified at lot level only, not the unit serial"
        ]

    async def test_converges_after_flag_cleared(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft 1", "draft 2"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="AGGREGATION FLAGS:\n- Missing item-to-case link\n"
                         "TRACEABILITY FLAGS: None detected\n"
                         "SALEABLE-RETURN FLAGS: None detected",
            ),
            make_review(
                9.0, approved=True,
                critique="AGGREGATION FLAGS: None detected\n"
                         "TRACEABILITY FLAGS: None detected\n"
                         "SALEABLE-RETURN FLAGS: None detected",
            ),
        ])
        wf = SerializationDSCSAWorkflow(
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
                critique="AGGREGATION FLAGS: None detected\n"
                         "TRACEABILITY FLAGS: None detected\n"
                         "SALEABLE-RETURN FLAGS: None detected",
            )
        ])
        wf = SerializationDSCSAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_description",
            "aggregation_flags",
            "traceability_flags",
            "saleable_return_flags",
            "serialization_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["serialization_checklist"][0] == (
            "[OWNER: Serialization / Supply-Chain Compliance]"
        )


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_present_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor(["draft"])
        reviewer = FakeReviewer([
            make_review(
                9.0, approved=True,
                critique="AGGREGATION FLAGS: None detected\n"
                         "TRACEABILITY FLAGS: None detected\n"
                         "SALEABLE-RETURN FLAGS: None detected",
            )
        ])
        wf = SerializationDSCSAWorkflow(
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
            "AGGREGATION FLAGS: None detected\n"
            "TRACEABILITY FLAGS: None detected\n"
            "SALEABLE-RETURN FLAGS: None detected"
        )
        reviewer = FakeReviewer([
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
            make_review(7.4, approved=False, critique=clean_critique),
        ])
        wf = SerializationDSCSAWorkflow(
            executor=executor, reviewer=reviewer, config=config
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 3
