"""Unit tests for AdverseEventTriageWorkflow — no live API calls.

Veto + triple-flag (D-HEALTH-2 / D-HEALTH-4). Mirrors test_drug_interaction_flagging.py shape:
- to_prompt_text renders all fields + per-field cap
- convergence on clean input
- non-convergence when severity flags present (3-round limit)
- veto halts loop with first_draft preserved
- no veto when directive is None
- all metadata keys present on clean run
- disclaimer in output on clean run
"""
from __future__ import annotations
from pathlib import Path
from typing import Any

import pytest

from adv_multi_agent.core.agents import ReviewResult
from adv_multi_agent.core.config import Config, ReviewerProvider
from adv_multi_agent.core.ledger import ClaimLedger
from adv_multi_agent.core.wiki import ResearchWiki
from adv_multi_agent.healthcare.workflows.adverse_event_triage import (
    AdverseEventTriageWorkflow,
    AdverseEventRequest,
    _DISCLAIMER,
    _MAX_FIELD_CHARS,
    _VETO_BANNER,
)
from .fakes import FakeExecutor, FakeReviewer


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


def make_review(score: float, *, approved: bool, critique: str = "") -> ReviewResult:
    return ReviewResult(score=score, critique=critique, suggestions=[], approved=approved)


def make_request(**kwargs: Any) -> AdverseEventRequest:
    defaults: dict[str, Any] = dict(
        product_name="Amoxicillin 500mg capsules",
        event_description=(
            "Patient developed severe anaphylaxis (urticaria, angioedema, "
            "bronchospasm, hypotension requiring epinephrine) within 15 minutes "
            "of first dose. Hospitalized; died 6 hours later despite resuscitation."
        ),
        patient_demographics="68-year-old male, weight 82kg, no prior allergy history documented",
        event_onset="Within 15 minutes of first dose on 2026-05-10",
        causality_assessment=(
            "Probable — strong temporal relationship (onset 15 min post-dose), "
            "dechallenge not applicable (fatal outcome), no alternative cause identified"
        ),
        concomitant_medications="Lisinopril 10mg daily, Metoprolol 50mg daily",
        outcome="Fatal — patient died 6 hours after event onset",
        prior_reports=(
            "Anaphylaxis to amoxicillin NOT listed in current USPI/SmPC as a known "
            "labeled ADR with fatal outcome; prior reports of hypersensitivity listed "
            "but fatal anaphylaxis is unlabeled per sponsor safety database review"
        ),
    )
    defaults.update(kwargs)
    return AdverseEventRequest(**defaults)


def clean_critique() -> str:
    return (
        "Adverse event triage thorough; severity graded against CTCAE; causality via WHO-UMC.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm MedDRA PT coding\n"
        "SEVERITY FLAGS: None detected\n"
        "CAUSALITY FLAGS: None detected\n"
        "REGULATORY FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Severity assessment
Anaphylaxis with fatal outcome: CTCAE Grade 5 (death). ICH E2A classification: Serious — fatal.
Life-threatening presentation prior to death (anaphylaxis with bronchospasm + hypotension): CTCAE Grade 4.

## Causality analysis
WHO-UMC causality: Probable — temporal association strong (onset 15 min), no alternative cause,
dechallenge not applicable (fatal). Naranjo score estimated 7 (probable).

## Regulatory-obligation determination
Fatal unexpected ADR with causality probable: 7-day expedited reporting obligation under ICH E2A
(FDA 21 CFR 312 / EMA EudraVigilance). Anaphylaxis with fatal outcome unlabeled per prior_reports.

## MedDRA coding
PT: Anaphylactic shock (10002199) / SOC: Immune system disorders (10021428).
Outcome: PT: Death (10011906).

## Recommended action
Initiate MedWatch expedited 7-day report immediately. Notify sponsor safety officer.
Assess USPI/SmPC for labeling update requirement.

## Claims
[Source: event_description] Anaphylaxis onset within 15 minutes of amoxicillin first dose.
[Source: causality_assessment] WHO-UMC causality: Probable — temporal + no alternative cause.
[Source: prior_reports] Fatal anaphylaxis unlabeled in current USPI/SmPC.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Product name:",
            "Event description:",
            "Patient demographics:",
            "Event onset:",
            "Causality assessment:",
            "Concomitant medications:",
            "Outcome:",
            "Prior reports:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(event_description=oversized).to_prompt_text()
        event_section = text.split("Event description:")[1].split("\n")[0]
        assert len(event_section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = AdverseEventTriageWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is True
        assert "veto_reason" not in result.metadata

    async def test_does_not_converge_when_severity_flags_present(self, tmp_path: Path) -> None:
        critique = (
            "Overall score: 7.5/10\n"
            "Key issues: severity not graded against CTCAE\n"
            "SEVERITY FLAGS:\n- Fatal outcome not graded as CTCAE Grade 5\n"
            "CAUSALITY FLAGS: None detected\n"
            "REGULATORY FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = AdverseEventTriageWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert len(result.metadata["severity_flags"]) == 1
        assert "CTCAE" in result.metadata["severity_flags"][0]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: serious unexpected ADR with fatal outcome triggers 7-day clock\n"
            "SEVERITY FLAGS: None detected\n"
            "CAUSALITY FLAGS: None detected\n"
            "REGULATORY FLAGS: None detected\n"
            "REVIEWER VETO: Fatal unexpected ADR — amoxicillin-induced anaphylaxis not in current "
            "labeling; causality probable; 7-day expedited FDA 21 CFR 312 / EMA EudraVigilance "
            "reporting clock triggered. Escalate to pharmacovigilance officer immediately."
        )
        config = make_config(tmp_path)
        wf = AdverseEventTriageWorkflow(
            executor=FakeExecutor(responses=["initial draft", "draft2", "draft3"]),
            reviewer=FakeReviewer(results=[make_review(9.0, approved=True, critique=veto_critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert result.rounds == 1
        assert "veto_reason" in result.metadata
        assert "Fatal" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = AdverseEventTriageWorkflow(
            executor=FakeExecutor(responses=["draft"]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert "veto_reason" not in result.metadata
        assert "vetoed" not in result.metadata


@pytest.mark.asyncio
class TestMetadata:
    async def test_metadata_includes_flag_lists_and_checklist(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = AdverseEventTriageWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "product_name",
            "severity_flags",
            "causality_flags",
            "regulatory_flags",
            "adverse_event_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["adverse_event_checklist"][0] == "[OWNER: Pharmacovigilance Officer / Drug Safety Scientist]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = AdverseEventTriageWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
