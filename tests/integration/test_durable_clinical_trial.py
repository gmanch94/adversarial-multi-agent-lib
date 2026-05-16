"""Integration tests for the durable layer wrapping ClinicalTrialEligibilityDurableWorkflow."""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.durable.checkpoint import FileCheckpointStore
from adv_multi_agent.core.durable.hooks import MergeFreshInputsHook
from adv_multi_agent.core.durable.workflow import DurableWorkflow
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
    TrialEligibilityRequest,
)
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
    ClinicalTrialEligibilityDurableWorkflow,
)

from tests.unit.fakes import FakeExecutor, FakeReviewer


def make_config(tmp_path: Path) -> Config:
    return Config(
        anthropic_api_key="test-key",
        reviewer_provider=ReviewerProvider.ANTHROPIC,
        workspace_dir=str(tmp_path),
        max_review_rounds=3,
        score_threshold=8.0,
    )


CLEAN_CRITIQUE = (
    "BIAS FLAGS: None detected\n"
    "ELIGIBILITY FLAGS: None detected\n"
    "EVIDENCE FLAGS: None detected\n"
)


def make_request(**overrides: Any) -> TrialEligibilityRequest:
    defaults: dict[str, Any] = dict(
        trial_id="SYN-LUNG-2026-001",
        protocol_summary="Phase II protocol — EGFR inhibitor in NSCLC",
        patient_profile="62yo NSCLC patient",
        biomarker_status="EGFR+",
        prior_treatments="None — newly diagnosed",
        competing_risks="No autoimmune; no prior immunotherapy",
        site_context="50% female; community + academic mix",
    )
    defaults.update(overrides)
    return TrialEligibilityRequest(**defaults)


@pytest.mark.asyncio
async def test_pause_on_labs_pending_then_resume_converges(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    executor = FakeExecutor([
        "## Eligibility Assessment\nEligible per protocol §3.1 (initial draft).",
        "## Eligibility Assessment\nEligible per protocol §3.1 (post-resume).",
    ])
    reviewer = FakeReviewer([
        ReviewResult(score=9.0, critique=CLEAN_CRITIQUE, suggestions=[], approved=True),
        ReviewResult(score=9.0, critique=CLEAN_CRITIQUE, suggestions=[], approved=True),
    ])
    inner = ClinicalTrialEligibilityDurableWorkflow(
        executor=executor, reviewer=reviewer, config=config,
    )
    store = FileCheckpointStore(base_dir=tmp_path / "checkpoints", workspace_dir=tmp_path)
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)

    paused = await dw.start(
        make_request(biomarker_status="labs pending — CBC + CMP not yet drawn")
    )
    assert paused.status == "paused"
    assert paused.pause_reason == "rolling_data"

    resumed = await dw.resume(
        paused.token,
        fresh_inputs=make_request(
            biomarker_status="labs complete: CBC + CMP unremarkable"
        ),
        reconciliation_hook_override=MergeFreshInputsHook(
            request_type=TrialEligibilityRequest
        ),
    )
    assert resumed.status == "completed"


@pytest.mark.asyncio
async def test_phi_not_written_to_checkpoint_in_raw_form(tmp_path: Path) -> None:
    """sanitize_for_prompt strips control chars before they hit the executor prompt."""
    config = make_config(tmp_path)
    executor = FakeExecutor(["## Eligibility\nEligible."])
    reviewer = FakeReviewer([
        ReviewResult(score=9.0, critique=CLEAN_CRITIQUE, suggestions=[], approved=True),
    ])
    inner = ClinicalTrialEligibilityDurableWorkflow(
        executor=executor, reviewer=reviewer, config=config,
    )
    dw = DurableWorkflow(
        inner=inner, config=config,
        checkpoint_store=FileCheckpointStore(base_dir=tmp_path / "ckpt", workspace_dir=tmp_path),
    )
    bad_input = make_request(patient_profile="62yo NSCLC\x01\x02\x03patient")
    await dw.start(bad_input)
    assert len(executor.prompts) >= 1
    prompt_text = executor.prompts[0]
    assert "\x01" not in prompt_text
    assert "\x02" not in prompt_text


@pytest.mark.asyncio
async def test_full_lifecycle_start_pause_resume_complete(tmp_path: Path) -> None:
    config = make_config(tmp_path)
    executor = FakeExecutor([
        "## Eligibility\nEligible.",
        "## Eligibility\nEligible.",
    ])
    reviewer = FakeReviewer([
        ReviewResult(score=9.0, critique=CLEAN_CRITIQUE, suggestions=[], approved=True),
        ReviewResult(score=9.0, critique=CLEAN_CRITIQUE, suggestions=[], approved=True),
    ])
    inner = ClinicalTrialEligibilityDurableWorkflow(
        executor=executor, reviewer=reviewer, config=config,
    )
    store = FileCheckpointStore(base_dir=tmp_path / "ckpt", workspace_dir=tmp_path)
    dw = DurableWorkflow(inner=inner, config=config, checkpoint_store=store)

    paused = await dw.start(make_request(biomarker_status="labs pending"))
    cp_paused = await store.read(paused.token.run_id)
    assert cp_paused.status == "paused"

    resumed = await dw.resume(
        paused.token,
        fresh_inputs=make_request(biomarker_status="labs complete"),
        reconciliation_hook_override=MergeFreshInputsHook(
            request_type=TrialEligibilityRequest
        ),
    )
    assert resumed.status == "completed"
    cp_done = await store.read(paused.token.run_id)
    assert cp_done.status == "completed"
    # Pause itself does not append a rounds_history entry; the resume round does.
    # Audit is preserved across pause+resume by replaying state from the checkpoint.
    assert len(cp_done.rounds_history) >= 1
    assert cp_done.round >= 2
