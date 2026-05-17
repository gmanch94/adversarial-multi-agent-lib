"""Integration test for D-DURABLE-4: workflow_version_hash changes when bundled
skill template bytes mutate. Covers the 21 CFR Part 11 attestation chain claim
that an edit to any clinical-trial skill template will be detected at resume."""
from __future__ import annotations

import pytest

from adv_multi_agent.core.config import Config
from adv_multi_agent.core.durable.workflow import DurableWorkflow


@pytest.fixture
def cfg() -> Config:
    return Config(
        executor_model="claude-opus-4-7",
        reviewer_model="gpt-4o",
        anthropic_api_key="test-key",
    )


def test_clinical_trial_hash_changes_when_template_byte_changes(
    cfg: Config, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Mutating a single byte of a bundled skill template changes the hash."""
    from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
        ClinicalTrialEligibilityDurableWorkflow,
    )

    inner = ClinicalTrialEligibilityDurableWorkflow(config=cfg)

    assert hasattr(inner, "workflow_version_inputs"), (
        "ClinicalTrialEligibilityDurableWorkflow lacks workflow_version_inputs() impl "
        "(D-DURABLE-4 21 CFR Part 11 attestation requirement)"
    )

    dw1 = DurableWorkflow(inner=inner, config=cfg)
    h1 = dw1._compute_workflow_version_hash()

    orig_inputs = list(inner.workflow_version_inputs())
    assert orig_inputs, "expected non-empty workflow_version_inputs from healthcare workflow"

    def mutated() -> list[bytes]:
        mutated_first = b"X" + orig_inputs[0][1:] if orig_inputs[0] else b"X"
        return [mutated_first] + orig_inputs[1:]

    monkeypatch.setattr(inner, "workflow_version_inputs", mutated)

    # New DurableWorkflow instance — cache must not carry over from dw1
    dw2 = DurableWorkflow(inner=inner, config=cfg)
    h2 = dw2._compute_workflow_version_hash()
    assert h1 != h2, "byte mutation in template did not change hash"


def test_clinical_trial_hash_deterministic_across_instances(cfg: Config) -> None:
    """Same workflow class + same templates → identical hash every time."""
    from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
        ClinicalTrialEligibilityDurableWorkflow,
    )

    h1 = DurableWorkflow(
        inner=ClinicalTrialEligibilityDurableWorkflow(config=cfg), config=cfg
    )._compute_workflow_version_hash()
    h2 = DurableWorkflow(
        inner=ClinicalTrialEligibilityDurableWorkflow(config=cfg), config=cfg
    )._compute_workflow_version_hash()
    assert h1 == h2
