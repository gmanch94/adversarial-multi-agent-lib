# Retail Domain Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a `retail/` domain with `DemandForecastWorkflow` and `LaborSchedulingWorkflow`, mirroring the `parole/` structure exactly.

**Architecture:** Two workflow files under `src/adv_multi_agent/retail/workflows/`, each with a typed input dataclass and domain-specific convergence gate (ASSUMPTION FLAGS / COMPLIANCE FLAGS). Nine skill templates in a flat `retail/skills/templates/` dir, prefixed by workflow. Two example scripts with synthetic data under `examples/retail/`.

**Tech Stack:** Python 3.11+, `anthropic` SDK, `pydantic` v2 (not used here — plain dataclasses like parole), `pytest`, `pytest-asyncio`.

---

## File Map

**Create:**
- `src/adv_multi_agent/retail/__init__.py`
- `src/adv_multi_agent/retail/workflows/__init__.py`
- `src/adv_multi_agent/retail/workflows/demand_forecasting.py`
- `src/adv_multi_agent/retail/workflows/labor_scheduling.py`
- `src/adv_multi_agent/retail/skills/__init__.py`
- `src/adv_multi_agent/retail/skills/templates/demand_signal.md`
- `src/adv_multi_agent/retail/skills/templates/demand_seasonality_audit.md`
- `src/adv_multi_agent/retail/skills/templates/demand_stockout_risk.md`
- `src/adv_multi_agent/retail/skills/templates/demand_weather_impact.md`
- `src/adv_multi_agent/retail/skills/templates/demand_unemployment_rate.md`
- `src/adv_multi_agent/retail/skills/templates/labor_schedule_draft.md`
- `src/adv_multi_agent/retail/skills/templates/labor_compliance_check.md`
- `src/adv_multi_agent/retail/skills/templates/labor_coverage_audit.md`
- `src/adv_multi_agent/retail/skills/templates/labor_unemployment_rate.md`
- `examples/retail/__init__.py`
- `examples/retail/demand_forecasting.py`
- `examples/retail/labor_scheduling.py`
- `tests/unit/test_demand_forecasting.py`
- `tests/unit/test_labor_scheduling.py`

**Modify:**
- `src/adv_multi_agent/__init__.py` — add retail exports
- `src/adv_multi_agent/core/skills/registry.py` — add `"retail"` to `bundled_skills_path` docstring

---

## Task 1: Scaffold retail package skeleton

**Files:**
- Create: `src/adv_multi_agent/retail/__init__.py`
- Create: `src/adv_multi_agent/retail/workflows/__init__.py`
- Create: `src/adv_multi_agent/retail/skills/__init__.py`

- [ ] **Step 1: Create the three `__init__.py` files**

`src/adv_multi_agent/retail/__init__.py`:
```python
"""
retail — adversarial multi-agent workflows for retail decision support.
"""
from .workflows.demand_forecasting import DemandForecastWorkflow, ForecastRequest
from .workflows.labor_scheduling import LaborSchedulingWorkflow, SchedulingRequest

__all__ = [
    "DemandForecastWorkflow",
    "ForecastRequest",
    "LaborSchedulingWorkflow",
    "SchedulingRequest",
]
```

`src/adv_multi_agent/retail/workflows/__init__.py`:
```python
"""Retail workflow implementations."""
```

`src/adv_multi_agent/retail/skills/__init__.py`:
```python
"""Retail skill templates package."""
```

- [ ] **Step 2: Create empty templates directory marker**

Create `src/adv_multi_agent/retail/skills/templates/.gitkeep` (empty file — placeholder until templates are added in Task 3).

- [ ] **Step 3: Verify imports work**

```bash
cd src && python -c "import adv_multi_agent.retail"
```

This will fail until Tasks 2 and 3 are done — that's expected. Skip if you prefer to verify after Task 2.

- [ ] **Step 4: Commit scaffold**

```bash
git add src/adv_multi_agent/retail/
git commit -m "feat(retail): scaffold retail package skeleton"
```

---

## Task 2: Implement `DemandForecastWorkflow`

**Files:**
- Create: `src/adv_multi_agent/retail/workflows/demand_forecasting.py`

- [ ] **Step 1: Write the failing test first**

Create `tests/unit/test_demand_forecasting.py`:

```python
"""Unit tests for DemandForecastWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.retail.workflows.demand_forecasting import (
    DemandForecastWorkflow,
    ForecastRequest,
    _DISCLAIMER,
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


def make_result(
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


def make_request(**kwargs: Any) -> ForecastRequest:
    defaults: dict[str, Any] = dict(
        store_id="KRO-OH-0042",
        sku="SKU-00123",
        product_category="dairy",
        historical_sales="Wk1:320 Wk2:310 Wk3:335 Wk4:340 Wk5:315 Wk6:328 Wk7:342 Wk8:330",
        current_inventory="on-hand: 180 units; in-transit: 200 units",
        lead_time_days="3",
        upcoming_events="Memorial Day weekend (Wk3); store loyalty promo -10% (Wk2)",
        seasonality_notes="Dairy demand rises ~8% May–Aug due to summer baking",
        weather_forecast="Warm and dry next 2 weeks; no precipitation expected",
        unemployment_rate="Local rate 4.2%, down 0.3pp YoY; consumer confidence stable",
    )
    defaults.update(kwargs)
    return ForecastRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> DemandForecastWorkflow:
    return DemandForecastWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Demand Signal Analysis
Baseline of ~330 units/week from 8-week history. Low variance (CV ~3%).

## Forecast
Wk1: 336 | Wk2: 302 (promo lift partially offset by -10% price) | Wk3: 370 (Memorial Day) | Wk4: 340

## Replenishment Recommendation
Order 480 units from supplier by Tuesday. Target delivery Thursday (3-day lead time).

## Key Assumptions
- Memorial Day lifts dairy ~15% based on historical holiday patterns.
- Promo reduces basket size but increases transactions; net -5% on unit volume.
- Weather has negligible impact on dairy demand.

## Evidence Gaps
No actuarial demand model baseline. Promotion uplift estimate is qualitative.

## Claims
[Source: historical_sales] Average weekly sales over 8 weeks: 327.5 units.
[Source: upcoming_events] Memorial Day weekend falls in forecast Wk3.
"""


class TestDemandConvergence:
    @pytest.mark.asyncio
    async def test_converges_when_score_meets_threshold_and_no_flags(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="ASSUMPTION FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert result.final_score == 8.0

    @pytest.mark.asyncio
    async def test_does_not_converge_when_assumption_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    8.0,
                    approved=True,
                    critique="ASSUMPTION FLAGS:\n- Memorial Day lift of 15% is unsubstantiated",
                ),
                make_result(8.0, approved=True, critique="ASSUMPTION FLAGS: None detected"),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2

    @pytest.mark.asyncio
    async def test_does_not_converge_when_score_below_threshold(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(6.0, approved=False, critique="Forecast not grounded."),
                make_result(6.5, approved=False, critique="Still weak."),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 2


class TestDemandOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="ASSUMPTION FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_metadata_keys_present(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="ASSUMPTION FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "store_id" in result.metadata
        assert "sku" in result.metadata
        assert "assumption_flags" in result.metadata
        assert "buyer_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata

    @pytest.mark.asyncio
    async def test_assumption_flags_empty_when_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="ASSUMPTION FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["assumption_flags"] == []

    @pytest.mark.asyncio
    async def test_assumption_flags_accumulated(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    7.0,
                    approved=False,
                    critique="ASSUMPTION FLAGS:\n- Holiday lift unsubstantiated",
                ),
                make_result(8.5, approved=True, critique="ASSUMPTION FLAGS: None detected"),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert any("Holiday lift" in f for f in result.metadata["assumption_flags"])


class TestExtractAssumptionFlags:
    def test_extracts_flags(self) -> None:
        critique = "Good.\n\nASSUMPTION FLAGS:\n- Holiday lift unsubstantiated\n- Weather factor unexplained\n\nOverall score: 6/10"
        flags = DemandForecastWorkflow._extract_assumption_flags(critique)
        assert len(flags) == 2
        assert "Holiday lift unsubstantiated" in flags

    def test_returns_empty_when_none_detected(self) -> None:
        critique = "ASSUMPTION FLAGS: None detected\nOverall score: 8/10"
        flags = DemandForecastWorkflow._extract_assumption_flags(critique)
        assert flags == []

    def test_returns_empty_when_section_absent(self) -> None:
        flags = DemandForecastWorkflow._extract_assumption_flags("No issues.")
        assert flags == []


class TestForecastRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        assert "Store: KRO-OH-0042" in text
        assert "SKU: SKU-00123" in text
        assert "Category: dairy" in text
        assert "Historical sales" in text
        assert "Current inventory" in text
        assert "Lead time" in text
        assert "Upcoming events" in text
        assert "Seasonality" in text
        assert "Weather forecast" in text
        assert "Unemployment rate" in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_demand_forecasting.py -v
```

Expected: `ModuleNotFoundError: No module named 'adv_multi_agent.retail'`

- [ ] **Step 3: Implement `demand_forecasting.py`**

Create `src/adv_multi_agent/retail/workflows/demand_forecasting.py`:

```python
"""
Workflow — Demand Forecasting (Retail Teaching Example)

Demonstrates the ARIS adversarial pattern for retail replenishment decisions.
Executor synthesizes a demand forecast; reviewer challenges assumptions and
flags any unsubstantiated adjustments under ASSUMPTION FLAGS.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. Live POS data — historical_sales is free-text; production requires
       integration with store transaction systems.
    2. Actuarial demand model — ML baseline (e.g. Prophet, LightGBM) should
       underpin the forecast; LLM adjusts the residual, not the baseline.
    3. Supplier API — lead_time_days should be fetched from supplier EDI/API
       in real time, not caller-supplied text.
    4. Cost model — stockout and overstock costs should be computed from
       actual margin and spoilage data, not qualitative assessment.
    5. Buyer approval gate — the replenishment order must not be placed
       automatically. A human buyer must review and confirm.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import sanitize_for_prompt
from ...core.workflow import BaseWorkflow, WorkflowResult

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated forecast is not a purchase order. "
    "A human buyer must review all assumptions independently and approve any "
    "replenishment action. AI output must never trigger automated ordering."
)

_FORECAST_REVIEW_CRITERIA = """\
Evaluate this demand forecast on five dimensions. Score each 0–10.

1. FORECAST GROUNDING (30%)
   Is the forecast anchored to the historical sales signal? Are week-over-week
   adjustments proportionate and direction-consistent with the stated drivers?
   Penalise forecasts that deviate from the baseline without evidence.

2. ASSUMPTION AUDIT (25%)
   Are all adjustments (seasonality, promotions, weather, events) explicitly
   stated and justified with evidence from the inputs? Flag every unsubstantiated
   assumption under ASSUMPTION FLAGS:. An assumption not present in the inputs
   is a flag even if plausible.

3. RISK BALANCE (25%)
   Does the replenishment recommendation balance stockout risk (lost sales,
   customer dissatisfaction) against overstock risk (spoilage, working capital)?
   Is the safety stock reasoning sound?

4. COMPLETENESS (10%)
   Are data gaps noted? Is forecast confidence expressed appropriately?
   Is the recommendation tied to a specific order quantity and date?

5. ACTIONABILITY (10%)
   Is the order recommendation specific enough for a buyer to act on:
   units, timing, supplier, delivery window?

Overall score = weighted average.
Score ≥ 7.5: forecast is ready for buyer review.
Score < 7.5: requires revision.

End your review with:
  Overall score: X/10
  Key issues: [bullet list]
  ASSUMPTION FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a demand forecast and replenishment recommendation for a human buyer.
You have no stake in the outcome. Your job is accuracy — not advocacy for a particular
order size.

BASE ALL ADJUSTMENTS ON THE INPUT DATA PROVIDED. Do not import assumptions from
general retail knowledge that are not grounded in the specific store, SKU, and
time-period data below.

STORE DATA:
{request_text}

{wiki_context}

Produce a structured forecast with exactly these sections:

## Demand Signal Analysis
Describe the baseline demand from historical sales. Identify trend direction,
variance, and any anomalies. State the average weekly run rate.

## Forecast
Four-week unit forecast, week by week. State each adjustment to the baseline
explicitly: driver, direction, magnitude, evidence source.

## Replenishment Recommendation
Specific: units to order, order-by date, expected delivery date (using stated
lead time), target post-delivery inventory level.

## Key Assumptions
One bullet per assumption. Each must be traceable to an input field.

## Evidence Gaps
Information missing from the inputs that would materially improve forecast
accuracy. Note the impact of each gap on confidence.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this demand forecast. Address EVERY issue in the reviewer's critique,
especially any ASSUMPTION FLAGS.

PREVIOUS FORECAST:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any flagged assumption: REMOVE the adjustment or replace it with
evidence directly present in the input data. Do not rephrase — remove or ground it.
"""


@dataclass
class ForecastRequest:
    """Structured input for the demand forecast workflow."""

    store_id: str
    """Store identifier, e.g. 'KRO-OH-0042'."""

    sku: str
    """SKU code for the product being forecast."""

    product_category: str
    """Category, e.g. 'dairy', 'produce', 'beverages'."""

    historical_sales: str
    """Free-text: units sold per week for the last 8 weeks, e.g. 'Wk1:320 Wk2:310 ...'"""

    current_inventory: str
    """On-hand and in-transit units."""

    lead_time_days: str
    """Supplier lead time in days."""

    upcoming_events: str
    """Local events, holidays, promotions in the next 4 weeks."""

    seasonality_notes: str
    """Known seasonal patterns for this SKU or category."""

    weather_forecast: str
    """Two-week weather outlook (temperature, precipitation)."""

    unemployment_rate: str
    """Local unemployment rate and trend — used as consumer spending signal."""

    def to_prompt_text(self) -> str:
        return "\n".join([
            f"Store: {self.store_id}",
            f"SKU: {self.sku}",
            f"Category: {self.product_category}",
            f"Historical sales (8 wk): {self.historical_sales}",
            f"Current inventory: {self.current_inventory}",
            f"Lead time: {self.lead_time_days} days",
            f"Upcoming events: {self.upcoming_events}",
            f"Seasonality: {self.seasonality_notes}",
            f"Weather forecast: {self.weather_forecast}",
            f"Unemployment rate: {self.unemployment_rate}",
        ])


class DemandForecastWorkflow(BaseWorkflow):
    """
    Adversarial demand forecasting: executor drafts forecast → reviewer
    challenges assumptions → iterate.

    Convergence gate: score ≥ threshold AND zero ASSUMPTION FLAGS.
    An assumption-laden-but-high-scoring forecast does not converge.

    Args:
        config: Standard Config. Cross-family provider pairing recommended.
    """

    async def run(  # type: ignore[override]
        self,
        request: ForecastRequest,
        **_: Any,
    ) -> WorkflowResult:
        """
        Run the adversarial forecast loop.

        Args:
            request: Structured store/SKU input.

        Returns:
            WorkflowResult:
              output          — Full forecast (markdown) + disclaimer.
              final_score     — Reviewer score on last round (0–10).
              converged       — True if score ≥ threshold AND no assumption flags.
              metadata        — store_id, sku, assumption_flags,
                                buyer_checklist, disclaimer, ledger_summary.
        """
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_flags: list[str] = []
        all_flags: list[str] = []
        max_claim_chars = getattr(config, "max_claim_text_chars", 1000)

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    request_text=request_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                flag_section = ""
                if current_flags:
                    flags_text = "\n".join(f"  - {f}" for f in current_flags)
                    flag_section = (
                        f"\n⚠️  ASSUMPTION FLAGS (remove or ground in input data):\n"
                        f"{flags_text}\n"
                    )
                prompt = _REVISION_PROMPT.format(
                    previous=sanitize_for_prompt(output, max_chars=10000),
                    score=f"{score:.1f}",
                    critique=sanitize_for_prompt(review.critique, max_chars=4000),
                    suggestions="\n".join(
                        f"- {sanitize_for_prompt(s, max_chars=500)}"
                        for s in review.suggestions
                    ),
                    flag_section=flag_section,
                    wiki_context=wiki_ctx,
                )

            output = await self.executor.run(prompt, context="")
            self._register_claims(output, round_num, max_claim_chars)

            review = await self.reviewer.review(
                output,
                criteria=_FORECAST_REVIEW_CRITERIA,
            )
            score = review.score
            current_flags = self._extract_assumption_flags(review.critique)
            all_flags.extend(current_flags)

            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=config.max_wiki_body_chars),
                round_num=round_num,
                score=score,
            )

            if review.approved and not current_flags:
                converged = True
                break

        buyer_checklist = self._build_buyer_checklist(request, all_flags)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "store_id": request.store_id,
                "sku": request.sku,
                "assumption_flags": list(dict.fromkeys(all_flags)),
                "buyer_checklist": buyer_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    def _register_claims(self, output: str, round_num: int, max_chars: int) -> None:
        if "## Claims" not in output:
            return
        claims_section = output.split("## Claims", 1)[1]
        existing = {c.text for c in self.ledger.all()}
        for raw_line in claims_section.splitlines():
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
            except ValueError:
                continue

    @staticmethod
    def _extract_assumption_flags(critique: str) -> list[str]:
        """
        Extract assumption flags from reviewer critique.
        Reviewer lists flags under 'ASSUMPTION FLAGS:'. Returns empty list
        if reviewer reports 'None detected' or section is absent.
        """
        if "ASSUMPTION FLAGS:" not in critique:
            return []
        section = critique.split("ASSUMPTION FLAGS:", 1)[1]
        flags: list[str] = []
        for line in section.splitlines():
            stripped = line.strip().lstrip("-•*").strip()
            if not stripped:
                continue
            if stripped.lower().startswith(("overall", "key issues", "#")):
                break
            if stripped.lower() in ("none detected", "none", "n/a"):
                return []
            flags.append(stripped)
        return flags

    @staticmethod
    def _build_buyer_checklist(
        request: ForecastRequest,
        assumption_flags: list[str],
    ) -> list[str]:
        checklist: list[str] = []
        if assumption_flags:
            checklist.append(
                f"[ ] ⚠️  ASSUMPTION FLAGS DETECTED ({len(assumption_flags)}) — "
                "verify each flagged assumption against store data before ordering"
            )
        checklist.extend([
            f"[ ] Verify historical sales data for {request.sku} in store {request.store_id}",
            "[ ] Confirm upcoming events and promotion dates are current",
            "[ ] Cross-check weather forecast against latest NWS data",
            "[ ] Validate lead time with supplier before placing order",
            "[ ] Review forecast against category manager's weekly guidance",
            "[ ] Approve replenishment order — AI output must not trigger auto-ordering",
        ])
        return checklist
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_demand_forecasting.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/adv_multi_agent/retail/workflows/demand_forecasting.py tests/unit/test_demand_forecasting.py
git commit -m "feat(retail): add DemandForecastWorkflow with tests"
```

---

## Task 3: Implement `LaborSchedulingWorkflow`

**Files:**
- Create: `src/adv_multi_agent/retail/workflows/labor_scheduling.py`
- Create: `tests/unit/test_labor_scheduling.py`

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_labor_scheduling.py`:

```python
"""Unit tests for LaborSchedulingWorkflow — no live API calls."""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.retail.workflows.labor_scheduling import (
    LaborSchedulingWorkflow,
    SchedulingRequest,
    _DISCLAIMER,
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


def make_result(
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


def make_request(**kwargs: Any) -> SchedulingRequest:
    defaults: dict[str, Any] = dict(
        store_id="KRO-OH-0042",
        week_start="2026-05-18",
        projected_traffic="Mon:1200 Tue:1100 Wed:1150 Thu:1300 Fri:1800 Sat:2400 Sun:1600; peaks: Fri 5-7pm, Sat 11am-2pm",
        staff_roster=(
            "Alice (cashier, FT, avail all week); Bob (cashier, PT, unavail Fri); "
            "Carol (produce, FT, avail all week); Dave (stocker, PT, avail Mon-Thu); "
            "Eve (manager, FT, avail all week)"
        ),
        labor_budget="$4,200 for the week",
        local_events="High school graduation Sat morning; no other events",
        state_labor_law_notes=(
            "Ohio: 18+ no minor restrictions; OT >40h/week at 1.5x; "
            "30-min unpaid break required for shifts >6h"
        ),
        unemployment_rate="Local rate 4.2%; moderate labor pool; turnover risk low this quarter",
    )
    defaults.update(kwargs)
    return SchedulingRequest(**defaults)


def make_workflow(
    config: Config,
    tmp_path: Path,
    executor: FakeExecutor,
    reviewer: FakeReviewer,
) -> LaborSchedulingWorkflow:
    return LaborSchedulingWorkflow(
        config=config,
        executor=executor,
        reviewer=reviewer,
        ledger=ClaimLedger(str(tmp_path / "ledger.json")),
        wiki=ResearchWiki(str(tmp_path / "wiki.json")),
    )


_GOOD_OUTPUT = """\
## Schedule
Mon: Eve 8-5 (mgr), Alice 9-6 (cash), Carol 7-4 (prod), Dave 6-2 (stock)
Tue: Eve 8-5, Alice 9-6, Carol 7-4, Dave 6-2
Wed: Eve 8-5, Alice 9-6, Carol 7-4, Dave 6-2
Thu: Eve 8-5, Alice 9-6, Carol 7-4, Dave 6-2
Fri: Eve 8-5, Alice 11-8 (peak coverage), Carol 7-4
Sat: Eve 7-4, Alice 9-6, Carol 7-4 (grad event)
Sun: Eve 10-6, Alice 10-6, Carol 9-5

## Coverage Analysis
Peak Fri 5-7pm: Alice + Eve on floor. Sat 11am-2pm: all three available.

## Labor Cost Estimate
Total hours: ~152. Estimated cost: $3,840 at avg $25.26/hr. Under $4,200 budget.

## Compliance Notes
All shifts ≤10h. Bob unavailability respected. No OT (Alice 38h, Eve 40h). All >6h shifts include break.

## Fairness Notes
FT staff (Alice, Eve, Carol) carry proportionate load. Dave (PT) at 32h — within availability.

## Evidence Gaps
No historical labor-to-sales ratio provided; coverage recommendations are estimated.

## Claims
[Source: staff_roster] Bob unavailable Friday — no Friday shift assigned.
[Source: state_labor_law_notes] OT threshold: >40h/week. Eve scheduled exactly 40h.
"""


class TestLaborConvergence:
    @pytest.mark.asyncio
    async def test_converges_when_score_meets_threshold_and_no_flags(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=3)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="COMPLIANCE FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 1
        assert result.final_score == 8.0

    @pytest.mark.asyncio
    async def test_does_not_converge_when_compliance_flags_present(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    8.0,
                    approved=True,
                    critique="COMPLIANCE FLAGS:\n- Alice scheduled 42h; exceeds 40h OT threshold",
                ),
                make_result(8.0, approved=True, critique="COMPLIANCE FLAGS: None detected"),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is True
        assert result.rounds == 2

    @pytest.mark.asyncio
    async def test_does_not_converge_when_score_below_threshold(
        self, tmp_path: Path
    ) -> None:
        config = make_config(tmp_path, score_threshold=7.5, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(6.0, approved=False, critique="Coverage gaps on Saturday."),
                make_result(6.5, approved=False, critique="Still understaffed at peak."),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 2


class TestLaborOutputStructure:
    @pytest.mark.asyncio
    async def test_output_contains_disclaimer(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="COMPLIANCE FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert _DISCLAIMER in result.output

    @pytest.mark.asyncio
    async def test_metadata_keys_present(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="COMPLIANCE FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert "store_id" in result.metadata
        assert "week_start" in result.metadata
        assert "compliance_flags" in result.metadata
        assert "manager_checklist" in result.metadata
        assert "disclaimer" in result.metadata
        assert "ledger_summary" in result.metadata

    @pytest.mark.asyncio
    async def test_compliance_flags_empty_when_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        executor = FakeExecutor([_GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [make_result(8.0, approved=True, critique="COMPLIANCE FLAGS: None detected")]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert result.metadata["compliance_flags"] == []

    @pytest.mark.asyncio
    async def test_compliance_flags_accumulated(self, tmp_path: Path) -> None:
        config = make_config(tmp_path, max_review_rounds=2)
        executor = FakeExecutor([_GOOD_OUTPUT, _GOOD_OUTPUT])
        reviewer = FakeReviewer(
            [
                make_result(
                    7.0,
                    approved=False,
                    critique="COMPLIANCE FLAGS:\n- Missing break for 8h shift",
                ),
                make_result(8.5, approved=True, critique="COMPLIANCE FLAGS: None detected"),
            ]
        )
        workflow = make_workflow(config, tmp_path, executor, reviewer)
        result = await workflow.run(request=make_request())
        assert any("break" in f.lower() for f in result.metadata["compliance_flags"])


class TestExtractComplianceFlags:
    def test_extracts_flags(self) -> None:
        critique = "Good coverage.\n\nCOMPLIANCE FLAGS:\n- Alice at 42h exceeds OT threshold\n- No break noted for 8h shift\n\nOverall score: 6/10"
        flags = LaborSchedulingWorkflow._extract_compliance_flags(critique)
        assert len(flags) == 2
        assert "Alice at 42h exceeds OT threshold" in flags

    def test_returns_empty_when_none_detected(self) -> None:
        critique = "COMPLIANCE FLAGS: None detected\nOverall score: 9/10"
        flags = LaborSchedulingWorkflow._extract_compliance_flags(critique)
        assert flags == []

    def test_returns_empty_when_section_absent(self) -> None:
        flags = LaborSchedulingWorkflow._extract_compliance_flags("Looks good.")
        assert flags == []


class TestSchedulingRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        req = make_request()
        text = req.to_prompt_text()
        assert "Store: KRO-OH-0042" in text
        assert "Week starting: 2026-05-18" in text
        assert "Projected traffic" in text
        assert "Staff roster" in text
        assert "Labor budget" in text
        assert "Local events" in text
        assert "Labor law" in text
        assert "Unemployment rate" in text
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/unit/test_labor_scheduling.py -v
```

Expected: `ModuleNotFoundError: No module named 'adv_multi_agent.retail.workflows.labor_scheduling'`

- [ ] **Step 3: Implement `labor_scheduling.py`**

Create `src/adv_multi_agent/retail/workflows/labor_scheduling.py`:

```python
"""
Workflow — Labor Scheduling (Retail Teaching Example)

Demonstrates the ARIS adversarial pattern for retail labor scheduling.
Executor drafts a weekly store schedule; reviewer challenges coverage,
compliance with stated labor laws, cost efficiency, and fairness.
Flags labor law violations under COMPLIANCE FLAGS.

⚠️  NOT FOR PRODUCTION DEPLOYMENT.
PRODUCTION_GAPS:
    1. HCM integration — staff_roster is free-text; production requires
       integration with HR / scheduling systems for real availability data.
    2. Automated labor law lookup — state_labor_law_notes is caller-supplied;
       production should pull rules from a jurisdiction database.
    3. Shift-swap and time-off handling — not modeled here.
    4. Payroll system write-back — schedule must not auto-publish.
    5. Manager approval gate — a store manager must review and publish
       the schedule; AI output must not go directly to employees.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ...core._internal import sanitize_for_prompt
from ...core.workflow import BaseWorkflow, WorkflowResult

_DISCLAIMER = (
    "⚠️  ADVISORY ONLY — This AI-generated schedule is not a published roster. "
    "A store manager must review for compliance, fairness, and operational fit "
    "before publishing. AI output must never be shown directly to employees."
)

_SCHEDULE_REVIEW_CRITERIA = """\
Evaluate this labor schedule on five dimensions. Score each 0–10.

1. COVERAGE (30%)
   Are all peak hours (as stated in projected_traffic) covered with adequate
   staffing by role? Are there identifiable gaps where customer-facing roles
   are understaffed relative to projected volume?

2. COMPLIANCE (25%) — CRITICAL
   Check every shift against the stated labor law rules. Flag each violation
   under COMPLIANCE FLAGS:. Examples to check:
     • Overtime: hours exceeding the stated weekly OT threshold
     • Break requirements: shifts exceeding the stated minimum without a break noted
     • Availability: staff scheduled on days they stated as unavailable
     • Any other rule explicitly stated in the labor_law_notes
   If no violations: "COMPLIANCE FLAGS: None detected"

3. COST EFFICIENCY (20%)
   Is total estimated labor cost within the stated budget? Is overtime
   minimized where coverage allows? Is the schedule free of unnecessary overlap?

4. FAIRNESS (15%)
   Are hours distributed proportionately between FT and PT staff given their
   stated availability? Are no staff members disproportionately burdened with
   undesirable shifts without justification?

5. ACTIONABILITY (10%)
   Is the schedule specific enough to post: named assignments, day, start time,
   end time, role? Could a manager copy this directly to the break room board?

Overall score = weighted average.
Score ≥ 7.5: schedule is ready for manager review.
Score < 7.5: requires revision.

End your review with:
  Overall score: X/10
  Key issues: [bullet list]
  COMPLIANCE FLAGS: [bullet list, or "None detected"]
"""

_INITIAL_PROMPT = """\
You are preparing a weekly store schedule for a human store manager to review.
You have no stake in the outcome. Your job is coverage, compliance, and fairness.

BASE ALL SCHEDULING DECISIONS ON THE INPUT DATA. Do not assume staff availability,
wage rates, or labor rules not stated in the inputs.

STORE DATA:
{request_text}

{wiki_context}

Produce a structured schedule with exactly these sections:

## Schedule
Day-by-day assignments: for each day, list each staff member's name, role,
start time, end time. One line per assignment.

## Coverage Analysis
For each stated peak window, confirm which staff members cover it and whether
coverage is adequate relative to projected volume.

## Labor Cost Estimate
Estimate total hours per staff member. Estimate weekly cost using a reasonable
average wage (state your assumption explicitly). Compare to stated budget.

## Compliance Notes
State compliance status for each labor law rule listed in the inputs.
Note any potential violations proactively.

## Fairness Notes
Assess hour distribution across FT and PT staff. Note any availability
constraints honored or missed.

## Evidence Gaps
Information not in the inputs that would improve schedule quality.

## Claims
One factual claim per line. Format: "[Source: <input_field>] <claim text>"
"""

_REVISION_PROMPT = """\
Revise this labor schedule. Address EVERY issue in the reviewer's critique,
especially any COMPLIANCE FLAGS.

PREVIOUS SCHEDULE:
{previous}

REVIEWER CRITIQUE (score: {score}/10):
{critique}

SPECIFIC ISSUES:
{suggestions}

{flag_section}

{wiki_context}

Revise using the same section structure.
⚠️  For any compliance flag: FIX the violation. Remove the offending shift
assignment and replace it with a compliant one. Do not note the violation
without fixing it.
"""


@dataclass
class SchedulingRequest:
    """Structured input for the labor scheduling workflow."""

    store_id: str
    """Store identifier, e.g. 'KRO-OH-0042'."""

    week_start: str
    """ISO date of week start (Monday), e.g. '2026-05-18'."""

    projected_traffic: str
    """Expected customer volume by day and peak hours, free-text."""

    staff_roster: str
    """Names, roles, FT/PT status, and availability constraints, free-text."""

    labor_budget: str
    """Weekly labor budget, e.g. '$4,200 for the week'."""

    local_events: str
    """Events that affect foot traffic during this week."""

    state_labor_law_notes: str
    """Applicable labor rules: OT threshold, break requirements, minor labor rules."""

    unemployment_rate: str
    """Local unemployment rate and trend — staffing pool and wage pressure signal."""

    def to_prompt_text(self) -> str:
        return "\n".join([
            f"Store: {self.store_id}",
            f"Week starting: {self.week_start}",
            f"Projected traffic: {self.projected_traffic}",
            f"Staff roster: {self.staff_roster}",
            f"Labor budget: {self.labor_budget}",
            f"Local events: {self.local_events}",
            f"Labor law (stated): {self.state_labor_law_notes}",
            f"Unemployment rate: {self.unemployment_rate}",
        ])


class LaborSchedulingWorkflow(BaseWorkflow):
    """
    Adversarial labor scheduling: executor drafts schedule → reviewer
    challenges coverage and compliance → iterate.

    Convergence gate: score ≥ threshold AND zero COMPLIANCE FLAGS.

    Args:
        config: Standard Config. Cross-family provider pairing recommended.
    """

    async def run(  # type: ignore[override]
        self,
        request: SchedulingRequest,
        **_: Any,
    ) -> WorkflowResult:
        """
        Run the adversarial scheduling loop.

        Returns:
            WorkflowResult:
              output           — Full schedule (markdown) + disclaimer.
              final_score      — Reviewer score on last round (0–10).
              converged        — True if score ≥ threshold AND no compliance flags.
              metadata         — store_id, week_start, compliance_flags,
                                 manager_checklist, disclaimer, ledger_summary.
        """
        config = self.config
        request_text = sanitize_for_prompt(request.to_prompt_text(), max_chars=6000)
        output = ""
        score = 0.0
        converged = False
        round_num = 0
        review = None
        current_flags: list[str] = []
        all_flags: list[str] = []
        max_claim_chars = getattr(config, "max_claim_text_chars", 1000)

        for round_num in range(1, config.max_review_rounds + 1):
            wiki_ctx = self.wiki.context_for_round(round_num)

            if round_num == 1:
                prompt = _INITIAL_PROMPT.format(
                    request_text=request_text,
                    wiki_context=wiki_ctx,
                )
            else:
                assert review is not None
                flag_section = ""
                if current_flags:
                    flags_text = "\n".join(f"  - {f}" for f in current_flags)
                    flag_section = (
                        f"\n⚠️  COMPLIANCE FLAGS (must be fixed, not noted):\n"
                        f"{flags_text}\n"
                    )
                prompt = _REVISION_PROMPT.format(
                    previous=sanitize_for_prompt(output, max_chars=10000),
                    score=f"{score:.1f}",
                    critique=sanitize_for_prompt(review.critique, max_chars=4000),
                    suggestions="\n".join(
                        f"- {sanitize_for_prompt(s, max_chars=500)}"
                        for s in review.suggestions
                    ),
                    flag_section=flag_section,
                    wiki_context=wiki_ctx,
                )

            output = await self.executor.run(prompt, context="")
            self._register_claims(output, round_num, max_claim_chars)

            review = await self.reviewer.review(
                output,
                criteria=_SCHEDULE_REVIEW_CRITERIA,
            )
            score = review.score
            current_flags = self._extract_compliance_flags(review.critique)
            all_flags.extend(current_flags)

            self.wiki.add_feedback(
                sanitize_for_prompt(review.critique, max_chars=config.max_wiki_body_chars),
                round_num=round_num,
                score=score,
            )

            if review.approved and not current_flags:
                converged = True
                break

        manager_checklist = self._build_manager_checklist(request, all_flags)

        return WorkflowResult(
            output=f"{output}\n\n---\n\n{_DISCLAIMER}",
            rounds=round_num,
            final_score=score,
            converged=converged,
            metadata={
                "store_id": request.store_id,
                "week_start": request.week_start,
                "compliance_flags": list(dict.fromkeys(all_flags)),
                "manager_checklist": manager_checklist,
                "disclaimer": _DISCLAIMER,
                "ledger_summary": self.ledger.summary(),
            },
        )

    def _register_claims(self, output: str, round_num: int, max_chars: int) -> None:
        if "## Claims" not in output:
            return
        claims_section = output.split("## Claims", 1)[1]
        existing = {c.text for c in self.ledger.all()}
        for raw_line in claims_section.splitlines():
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
            except ValueError:
                continue

    @staticmethod
    def _extract_compliance_flags(critique: str) -> list[str]:
        """
        Extract compliance flags from reviewer critique.
        Reviewer lists violations under 'COMPLIANCE FLAGS:'. Returns empty
        list if reviewer reports 'None detected' or section is absent.
        """
        if "COMPLIANCE FLAGS:" not in critique:
            return []
        section = critique.split("COMPLIANCE FLAGS:", 1)[1]
        flags: list[str] = []
        for line in section.splitlines():
            stripped = line.strip().lstrip("-•*").strip()
            if not stripped:
                continue
            if stripped.lower().startswith(("overall", "key issues", "#")):
                break
            if stripped.lower() in ("none detected", "none", "n/a"):
                return []
            flags.append(stripped)
        return flags

    @staticmethod
    def _build_manager_checklist(
        request: SchedulingRequest,
        compliance_flags: list[str],
    ) -> list[str]:
        checklist: list[str] = []
        if compliance_flags:
            checklist.append(
                f"[ ] ⚠️  COMPLIANCE FLAGS DETECTED ({len(compliance_flags)}) — "
                "resolve ALL violations before publishing schedule"
            )
        checklist.extend([
            f"[ ] Verify staff availability for week of {request.week_start}",
            "[ ] Confirm all shifts comply with state labor law requirements",
            "[ ] Check total hours per employee against OT threshold",
            "[ ] Verify budget: total estimated cost vs. approved labor budget",
            "[ ] Review peak coverage for projected high-traffic periods",
            "[ ] Publish schedule — AI output must not go directly to employees",
        ])
        return checklist
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/unit/test_labor_scheduling.py -v
```

Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add src/adv_multi_agent/retail/workflows/labor_scheduling.py tests/unit/test_labor_scheduling.py
git commit -m "feat(retail): add LaborSchedulingWorkflow with tests"
```

---

## Task 4: Add 9 skill templates

**Files:**
- Create: `src/adv_multi_agent/retail/skills/templates/demand_signal.md`
- Create: `src/adv_multi_agent/retail/skills/templates/demand_seasonality_audit.md`
- Create: `src/adv_multi_agent/retail/skills/templates/demand_stockout_risk.md`
- Create: `src/adv_multi_agent/retail/skills/templates/demand_weather_impact.md`
- Create: `src/adv_multi_agent/retail/skills/templates/demand_unemployment_rate.md`
- Create: `src/adv_multi_agent/retail/skills/templates/labor_schedule_draft.md`
- Create: `src/adv_multi_agent/retail/skills/templates/labor_compliance_check.md`
- Create: `src/adv_multi_agent/retail/skills/templates/labor_coverage_audit.md`
- Create: `src/adv_multi_agent/retail/skills/templates/labor_unemployment_rate.md`

- [ ] **Step 1: Create demand skill templates**

`demand_signal.md`:
```markdown
---
name: demand_signal
description: Analyse historical sales signal and compute baseline weekly run rate for a retail SKU
inputs: [historical_sales, product_category, store_id]
---
You are a demand analyst. Analyse the historical sales data below and produce a baseline demand signal.

Store: {store_id}
Category: {product_category}
Historical sales (8 weeks): {historical_sales}

Compute:
1. **Average weekly run rate** — mean units/week across all provided weeks
2. **Trend** — is demand rising, falling, or flat? State slope direction and approximate rate
3. **Variance** — coefficient of variation (CV = std/mean). Flag if CV > 15% as high-variance
4. **Anomalies** — any week deviating >20% from mean? Note the week and magnitude

Output format:
- Run rate: X units/week
- Trend: [Rising/Flat/Falling] at ~Y units/week
- CV: Z% ([Low/Moderate/High] variance)
- Anomalies: [list or "None detected"]
- Confidence in baseline: [High/Moderate/Low] with one-sentence justification
```

`demand_seasonality_audit.md`:
```markdown
---
name: demand_seasonality_audit
description: Challenge seasonality assumptions in a demand forecast for a retail SKU
inputs: [product_category, seasonality_notes, upcoming_events, forecast_adjustments]
---
You are a demand planning auditor. Challenge the seasonality assumptions below.

Category: {product_category}
Stated seasonality notes: {seasonality_notes}
Upcoming events: {upcoming_events}
Forecast adjustments being challenged: {forecast_adjustments}

For each seasonal or event-based adjustment, evaluate:
1. **Is the adjustment direction correct?** (e.g. does summer actually lift dairy?)
2. **Is the magnitude justified?** State whether the stated % lift/drop is reasonable
3. **Is the timing correct?** Does the adjustment apply to the right forecast weeks?
4. **Is the evidence grounded in the inputs?** Flag adjustments that rely on general
   retail knowledge not present in the stated seasonality_notes or upcoming_events

Output as a bullet list per adjustment:
- Adjustment: [name]
  - Direction: [Correct/Questionable] — [reason]
  - Magnitude: [Justified/Overstated/Understated] — [reason]
  - Timing: [Correct/Off by N weeks]
  - Grounded: [Yes/No] — [flag text if No]
```

`demand_stockout_risk.md`:
```markdown
---
name: demand_stockout_risk
description: Evaluate stockout vs. overstock risk for a retail replenishment decision
inputs: [sku, product_category, current_inventory, lead_time_days, forecast_units, order_quantity]
---
You are a supply chain risk analyst. Evaluate the risk balance for this replenishment decision.

SKU: {sku}
Category: {product_category}
Current inventory: {current_inventory}
Supplier lead time: {lead_time_days} days
4-week demand forecast: {forecast_units} units
Proposed order quantity: {order_quantity} units

Assess:
1. **Days of supply** — at the forecast run rate, how many days does current inventory cover?
2. **Stockout window** — if the order arrives on day (lead_time_days), will inventory run out before delivery?
3. **Post-order inventory** — projected on-hand after order arrives. Is it excessive for the category?
   (Dairy: max 10-14 days; Produce: max 3-5 days; Dry goods: max 30-45 days)
4. **Safety stock adequacy** — does the order recommendation include buffer for forecast error?

Output:
- Days of supply (current): X days
- Stockout risk: [High/Moderate/Low] — [reason]
- Overstock risk: [High/Moderate/Low] — [reason]
- Recommendation: [Increase order / Maintain / Reduce order] by ~N units, with justification
```

`demand_weather_impact.md`:
```markdown
---
name: demand_weather_impact
description: Assess weather forecast impact on retail demand for a specific SKU and category
inputs: [product_category, weather_forecast, historical_sales]
---
You are a demand analyst assessing weather-driven demand variation.

Category: {product_category}
Weather forecast (2 weeks): {weather_forecast}
Historical sales baseline: {historical_sales}

Assess the weather impact on demand:
1. **Direction** — does the forecasted weather increase or decrease demand for this category?
   Use only the stated weather data. Do not import general retail weather rules not supported
   by the forecast.
2. **Magnitude** — estimate % demand change. State your reasoning explicitly.
   If you cannot justify a specific % from the stated forecast, say "Insufficient data to quantify."
3. **Timing** — which forecast weeks are most affected?
4. **Confidence** — how certain is the weather-demand link for this category? Note if the
   relationship is weak (e.g. weather rarely affects centre-aisle dry goods).

Output:
- Weather impact direction: [Positive/Negative/Neutral]
- Estimated magnitude: [X% or "Insufficient data to quantify"]
- Peak impact week(s): [Wk N or "Spread evenly"]
- Confidence: [High/Moderate/Low] — [one sentence]
```

`demand_unemployment_rate.md`:
```markdown
---
name: demand_unemployment_rate
description: Assess local unemployment rate as a consumer spending signal for retail demand forecasting
inputs: [product_category, unemployment_rate, store_id]
---
You are a retail economist. Assess the consumer spending signal from the local unemployment data.

Store: {store_id}
Category: {product_category}
Local unemployment data: {unemployment_rate}

Assess:
1. **Spending sensitivity** — is this category sensitive to local employment conditions?
   (Staples like dairy/produce: low sensitivity. Discretionary/premium: moderate-high.)
2. **Direction** — does the current rate and trend suggest spending headwinds or tailwinds?
3. **Magnitude** — estimate whether the unemployment signal warrants a demand adjustment of
   more than ±2%. If not material, say so explicitly.
4. **Confidence** — how confident are you that local unemployment is a meaningful signal
   for this store and category? Note confounders (e.g. store serves a university town;
   seasonal worker population).

Output:
- Category spending sensitivity: [Low/Moderate/High]
- Signal direction: [Headwind/Neutral/Tailwind]
- Recommended demand adjustment: [+X% / No adjustment / -X%]
- Confidence: [High/Moderate/Low] — [one sentence]
```

- [ ] **Step 2: Create labor skill templates**

`labor_schedule_draft.md`:
```markdown
---
name: labor_schedule_draft
description: Draft a weekly store schedule from staff roster and projected traffic
inputs: [store_id, week_start, staff_roster, projected_traffic, labor_budget]
---
You are a retail scheduling assistant. Draft a weekly schedule for manager review.

Store: {store_id}
Week starting: {week_start}
Projected traffic: {projected_traffic}
Staff roster and availability: {staff_roster}
Labor budget: {labor_budget}

Rules:
- Respect every stated availability constraint. A staff member marked unavailable on a day
  must not appear in the schedule for that day.
- Match staffing levels to projected traffic: assign more staff on high-volume days and during
  peak windows.
- Do not schedule staff beyond their FT/PT hour limits without explicit justification.

Output format (one line per assignment):
[Day]: [Name] [start]-[end] ([role])

Then add:
- Estimated hours per staff member
- Estimated total labor cost (state your assumed hourly wage per role)
- Whether estimate is within the stated budget
```

`labor_compliance_check.md`:
```markdown
---
name: labor_compliance_check
description: Check a draft store schedule against stated labor law rules for compliance violations
inputs: [schedule_text, state_labor_law_notes, staff_roster]
---
You are a labor compliance auditor. Check the schedule below against the stated rules.

Schedule:
{schedule_text}

Stated labor law rules:
{state_labor_law_notes}

Staff roster (for FT/PT and availability reference):
{staff_roster}

Check each rule explicitly stated in state_labor_law_notes:
1. For each staff member, compute total scheduled hours. Flag if OT threshold is exceeded.
2. For each shift exceeding the stated break threshold, confirm a break is noted.
3. Verify no staff member is scheduled on a day they stated as unavailable.
4. Note any other violation of an explicitly stated rule.

Output:
- [PASS] or [FAIL] for each rule checked, with the rule name and staff member affected
- Summary: [X violations found / No violations found]
- COMPLIANCE FLAGS: [bullet list of violations, or "None detected"]
```

`labor_coverage_audit.md`:
```markdown
---
name: labor_coverage_audit
description: Audit peak hour coverage in a draft store schedule against projected traffic
inputs: [schedule_text, projected_traffic, staff_roster]
---
You are a retail operations analyst. Audit whether the schedule adequately covers peak periods.

Schedule:
{schedule_text}

Projected traffic (with peak windows):
{projected_traffic}

Staff roster (roles):
{staff_roster}

For each stated peak window:
1. List which staff members are on shift during that window
2. Identify the roles present (cashier, produce, stocker, manager)
3. Assess whether coverage is adequate relative to the projected volume
4. Flag any peak window with fewer than 2 customer-facing staff as UNDERSTAFFED

Output as a table:
| Peak window | Staff on shift | Roles covered | Coverage assessment |
|---|---|---|---|

Then:
- Overall coverage: [Adequate/Gaps identified]
- Gaps: [list peak windows flagged as UNDERSTAFFED, or "None"]
```

`labor_unemployment_rate.md`:
```markdown
---
name: labor_unemployment_rate
description: Assess local unemployment rate as a staffing pool and wage pressure signal for retail labor scheduling
inputs: [store_id, unemployment_rate, staff_roster]
---
You are a retail HR analyst. Assess the labor market signal from local unemployment data.

Store: {store_id}
Local unemployment data: {unemployment_rate}
Current staff roster: {staff_roster}

Assess:
1. **Staffing pool** — does the local rate suggest it is easy or difficult to find replacement
   or additional staff quickly? (High unemployment → easier; low → harder)
2. **Turnover risk** — does the trend suggest staff are likely to leave for other opportunities?
   (Falling unemployment, tight market → higher turnover risk)
3. **Wage pressure** — does the market suggest current wage rates are above, at, or below
   market? High tightness may require above-market offers for open roles.
4. **Scheduling implication** — does the labor market signal warrant any change to how the
   schedule is built? (e.g. build in more cross-training flexibility; reduce reliance on PT
   staff who may leave)

Output:
- Labor pool availability: [Ample/Moderate/Tight]
- Turnover risk: [Low/Moderate/High]
- Wage pressure: [Below market/At market/Above market pressure]
- Scheduling implication: [one actionable sentence, or "No near-term implication"]
```

- [ ] **Step 3: Delete the `.gitkeep` placeholder**

```bash
rm src/adv_multi_agent/retail/skills/templates/.gitkeep
```

- [ ] **Step 4: Verify skill registry loads them**

```python
# Run this in the project root:
python -c "
from adv_multi_agent.core.skills.registry import SkillRegistry
path = SkillRegistry.bundled_skills_path(domain='retail')
reg = SkillRegistry(str(path))
print(reg.describe())
"
```

Expected output lists 9 skills: `demand_signal`, `demand_seasonality_audit`, `demand_stockout_risk`, `demand_weather_impact`, `demand_unemployment_rate`, `labor_schedule_draft`, `labor_compliance_check`, `labor_coverage_audit`, `labor_unemployment_rate`.

Note: `bundled_skills_path(domain='retail')` will work because it dynamically resolves `adv_multi_agent.retail.skills` — no code change needed in `registry.py`.

- [ ] **Step 5: Commit**

```bash
git add src/adv_multi_agent/retail/skills/
git commit -m "feat(retail): add 9 skill templates (demand + labor)"
```

---

## Task 5: Wire retail into top-level exports

**Files:**
- Modify: `src/adv_multi_agent/__init__.py`

- [ ] **Step 1: Add retail imports and exports**

In `src/adv_multi_agent/__init__.py`, add after the parole import:

```python
from .retail.workflows.demand_forecasting import DemandForecastWorkflow, ForecastRequest
from .retail.workflows.labor_scheduling import LaborSchedulingWorkflow, SchedulingRequest
```

And add to `__all__`:
```python
    "DemandForecastWorkflow",
    "ForecastRequest",
    "LaborSchedulingWorkflow",
    "SchedulingRequest",
```

- [ ] **Step 2: Verify top-level import**

```bash
python -c "from adv_multi_agent import DemandForecastWorkflow, LaborSchedulingWorkflow, ForecastRequest, SchedulingRequest; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Run full test suite**

```bash
pytest tests/unit/ -v
```

Expected: all existing tests pass plus the new retail tests.

- [ ] **Step 4: Commit**

```bash
git add src/adv_multi_agent/__init__.py
git commit -m "feat(retail): export retail workflows from top-level package"
```

---

## Task 6: Add example scripts

**Files:**
- Create: `examples/retail/__init__.py`
- Create: `examples/retail/demand_forecasting.py`
- Create: `examples/retail/labor_scheduling.py`

- [ ] **Step 1: Create `examples/retail/__init__.py`**

```python
"""Retail workflow examples."""
```

- [ ] **Step 2: Create `examples/retail/demand_forecasting.py`**

```python
"""
Demand Forecast example — runs DemandForecastWorkflow with synthetic Kroger data.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.retail.demand_forecasting
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.retail.workflows.demand_forecasting import (
    DemandForecastWorkflow,
    ForecastRequest,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = ForecastRequest(
        store_id="KRO-OH-0042",
        sku="SKU-88210-MILK2PCT",
        product_category="dairy",
        historical_sales=(
            "Wk1:320 Wk2:310 Wk3:335 Wk4:340 "
            "Wk5:315 Wk6:328 Wk7:342 Wk8:330"
        ),
        current_inventory="on-hand: 180 units; in-transit: 200 units (arrives Thu)",
        lead_time_days="3",
        upcoming_events=(
            "Memorial Day weekend in Wk3 (Mon holiday, high grilling traffic); "
            "store loyalty promo -10% on dairy Wk2 only"
        ),
        seasonality_notes=(
            "Dairy demand historically rises 6–10% May–Aug in this region "
            "due to summer baking and outdoor entertaining. "
            "2% milk is the top-selling dairy SKU."
        ),
        weather_forecast=(
            "Warm and dry next 14 days; highs 78–84°F; "
            "no precipitation forecast. Typical late-May Ohio pattern."
        ),
        unemployment_rate=(
            "Franklin County OH: 4.2% (Apr 2026), down 0.3pp YoY. "
            "Consumer confidence index 102 (stable). "
            "No major employer layoffs in the past 90 days."
        ),
    )

    workflow = DemandForecastWorkflow(config=config)
    result = await workflow.run(request=request)

    print(f"Converged: {result.converged} | Rounds: {result.rounds} | Score: {result.final_score:.1f}/10")
    print(f"Store: {result.metadata['store_id']} | SKU: {result.metadata['sku']}")
    print()
    print(result.output)
    print()
    print("--- Buyer Checklist ---")
    for item in result.metadata["buyer_checklist"]:
        print(item)
    if result.metadata["assumption_flags"]:
        print("\n--- Assumption Flags ---")
        for flag in result.metadata["assumption_flags"]:
            print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 3: Create `examples/retail/labor_scheduling.py`**

```python
"""
Labor Scheduling example — runs LaborSchedulingWorkflow with synthetic Kroger data.

Usage:
    ANTHROPIC_API_KEY=... OPENAI_API_KEY=... python -m examples.retail.labor_scheduling
"""
from __future__ import annotations

import asyncio

from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.retail.workflows.labor_scheduling import (
    LaborSchedulingWorkflow,
    SchedulingRequest,
)


async def main() -> None:
    config = Config(
        reviewer_provider=ReviewerProvider.OPENAI,
        max_review_rounds=3,
        score_threshold=7.5,
    )

    request = SchedulingRequest(
        store_id="KRO-OH-0042",
        week_start="2026-05-18",
        projected_traffic=(
            "Mon: 1,200 customers; Tue: 1,100; Wed: 1,150; Thu: 1,300; "
            "Fri: 1,800 (peak 5–7pm); Sat: 2,400 (peak 11am–2pm); Sun: 1,600. "
            "Busiest day: Saturday due to high school graduation in the area."
        ),
        staff_roster=(
            "Alice Chen — cashier, FT (40h/wk), available all 7 days; "
            "Bob Torres — cashier, PT (20h/wk), unavailable Friday; "
            "Carol Singh — produce specialist, FT, available all 7 days; "
            "Dave Kim — overnight stocker, PT (32h/wk), available Mon–Thu only; "
            "Eve Johnson — store manager, FT, available all 7 days"
        ),
        labor_budget="$4,200 for the week (including all wages and benefits est.)",
        local_events=(
            "Jefferson High School graduation ceremony Saturday 10am–12pm, "
            "held 0.3 miles from store. Expect elevated Sat AM traffic. "
            "No other scheduled events this week."
        ),
        state_labor_law_notes=(
            "Ohio (18+ employees): "
            "OT rate 1.5x applies to all hours over 40/week; "
            "30-minute unpaid break required for any shift exceeding 6 hours; "
            "no minor labor restrictions (all staff are 18+); "
            "minimum wage $10.45/hr (all staff above this rate)"
        ),
        unemployment_rate=(
            "Franklin County OH: 4.2% (Apr 2026), down 0.3pp YoY. "
            "Retail sector hiring is competitive; two new stores opened in the trade area Q1. "
            "PT staff turnover risk: moderate."
        ),
    )

    workflow = LaborSchedulingWorkflow(config=config)
    result = await workflow.run(request=request)

    print(f"Converged: {result.converged} | Rounds: {result.rounds} | Score: {result.final_score:.1f}/10")
    print(f"Store: {result.metadata['store_id']} | Week: {result.metadata['week_start']}")
    print()
    print(result.output)
    print()
    print("--- Manager Checklist ---")
    for item in result.metadata["manager_checklist"]:
        print(item)
    if result.metadata["compliance_flags"]:
        print("\n--- Compliance Flags ---")
        for flag in result.metadata["compliance_flags"]:
            print(f"  • {flag}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 4: Verify examples are importable**

```bash
python -c "import examples.retail.demand_forecasting; import examples.retail.labor_scheduling; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Run full test suite one final time**

```bash
pytest tests/unit/ -v --tb=short
```

Expected: all tests pass (181 existing + new retail tests).

- [ ] **Step 6: Final commit**

```bash
git add examples/retail/
git commit -m "feat(retail): add demand forecasting and labor scheduling examples"
```

---

## Self-Review

**Spec coverage check:**
- ✅ `retail/` domain with two workflows — Tasks 2, 3
- ✅ `ForecastRequest` with all 10 fields including `weather_forecast` + `unemployment_rate` — Task 2
- ✅ `SchedulingRequest` with all 8 fields including `unemployment_rate` — Task 3
- ✅ ASSUMPTION FLAGS convergence gate (demand) — Task 2
- ✅ COMPLIANCE FLAGS convergence gate (labor) — Task 3
- ✅ 9 skill templates, flat, prefixed — Task 4
- ✅ 2 example scripts with synthetic Kroger data — Task 6
- ✅ Top-level exports — Task 5
- ✅ Production gaps in each module docstring — Tasks 2, 3
- ✅ Mirrors parole pattern: `_DISCLAIMER`, `_build_*_checklist`, `_extract_*_flags`, `_register_claims` — Tasks 2, 3

**Placeholder scan:** No TBDs. All code blocks are complete.

**Type consistency:**
- `ForecastRequest` defined Task 2, used in Task 2 tests and Task 6 — consistent
- `SchedulingRequest` defined Task 3, used in Task 3 tests and Task 6 — consistent
- `DemandForecastWorkflow._extract_assumption_flags` — defined and tested in Task 2 ✅
- `LaborSchedulingWorkflow._extract_compliance_flags` — defined and tested in Task 3 ✅
- `result.metadata["assumption_flags"]` / `result.metadata["compliance_flags"]` — consistent across workflow and tests ✅
- `result.metadata["buyer_checklist"]` / `result.metadata["manager_checklist"]` — consistent ✅
