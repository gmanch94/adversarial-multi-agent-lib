"""Unit tests for DrugInteractionFlaggingWorkflow — no live API calls.

Veto + triple-flag (D-HEALTH-2). Mirrors test_product_liability_root_cause.py shape:
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
from adv_multi_agent.healthcare.workflows.drug_interaction_flagging import (
    DrugInteractionFlaggingWorkflow,
    DrugInteractionRequest,
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


def make_request(**kwargs: Any) -> DrugInteractionRequest:
    defaults: dict[str, Any] = dict(
        patient_id="PT-2026-04812",
        medication_list="warfarin 5mg daily; metoprolol 50mg BID; lisinopril 10mg daily",
        new_medication="ibuprofen 600mg q6h prn (proposed for OA flare)",
        indication="osteoarthritis pain flare, NSAID requested by patient",
        renal_function="eGFR 58 mL/min/1.73m2 (CKD3a)",
        hepatic_function="LFTs WNL; no cirrhosis",
        allergy_history="no documented drug allergies",
        formulary_reference=(
            "Lexicomp interaction monograph: warfarin + NSAID = major; "
            "INR + bleeding risk increase 3-7 fold"
        ),
    )
    defaults.update(kwargs)
    return DrugInteractionRequest(**defaults)


def clean_critique() -> str:
    return (
        "Interaction analysis thorough and grounded in formulary reference.\n\n"
        "Overall score: 8.5/10\n"
        "Key issues:\n- Confirm renal dose ceiling\n"
        "SEVERITY FLAGS: None detected\n"
        "EVIDENCE FLAGS: None detected\n"
        "CONTRAINDICATION FLAGS: None detected\n"
        "REVIEWER VETO: None\n"
    )


_GOOD_OUTPUT = """\
## Interaction analysis
Warfarin + ibuprofen: major interaction per Lexicomp; INR increase + GI bleed risk.
Metoprolol + ibuprofen: minor; NSAIDs may attenuate antihypertensive effect.
Lisinopril + ibuprofen: moderate; NSAID may reduce ACE inhibitor efficacy and worsen renal function.

## Severity grading
Warfarin + NSAID: MAJOR (Lexicomp warfarin + NSAID monograph — INR + bleeding risk 3-7 fold).
Metoprolol + NSAID: MINOR.
Lisinopril + NSAID: MODERATE.

## Contraindication check
Drug-drug: warfarin + ibuprofen — clinical contraindication per formulary.
Drug-condition: eGFR 58 (CKD3a) — NSAID use may worsen renal function; caution required.
Drug-allergy: no documented allergy to NSAID class.

## Dose-adjustment recommendation
Renal function eGFR 58: ibuprofen not recommended in CKD3; if NSAID required, use lowest dose
with close renal monitoring. No hepatic dose adjustment needed (LFTs WNL).

## Claims
[Source: formulary_reference] warfarin + NSAID = major interaction per Lexicomp.
[Source: renal_function] eGFR 58 CKD3a — NSAID contraindicated per renal dosing guidance.
"""


class TestRequestToPromptText:
    def test_contains_all_fields(self) -> None:
        text = make_request().to_prompt_text()
        for fragment in [
            "Patient ID:",
            "Medication list:",
            "New medication:",
            "Indication:",
            "Renal function:",
            "Hepatic function:",
            "Allergy history:",
            "Formulary reference:",
        ]:
            assert fragment in text

    def test_per_field_cap_truncates_oversized(self) -> None:
        oversized = "x" * (_MAX_FIELD_CHARS + 500)
        text = make_request(formulary_reference=oversized).to_prompt_text()
        formulary_section = text.split("Formulary reference:")[1].split("\n")[0]
        assert len(formulary_section.strip()) <= _MAX_FIELD_CHARS


@pytest.mark.asyncio
class TestConvergence:
    async def test_converges_clean(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = DrugInteractionFlaggingWorkflow(
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
            "Key issues: severity not grounded in formulary\n"
            "SEVERITY FLAGS:\n- warfarin + NSAID severity not cited from supplied monograph\n"
            "EVIDENCE FLAGS: None detected\n"
            "CONTRAINDICATION FLAGS: None detected\n"
            "REVIEWER VETO: None\n"
        )
        config = make_config(tmp_path, max_review_rounds=1)
        wf = DrugInteractionFlaggingWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(7.5, approved=True, critique=critique)]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert result.converged is False
        assert len(result.metadata["severity_flags"]) == 1
        assert "warfarin" in result.metadata["severity_flags"][0]


@pytest.mark.asyncio
class TestVeto:
    async def test_veto_halts_loop(self, tmp_path: Path) -> None:
        veto_critique = (
            "Overall score: 9.0/10\n"
            "Key issues: absolute contraindication present\n"
            "SEVERITY FLAGS: None detected\n"
            "EVIDENCE FLAGS: None detected\n"
            "CONTRAINDICATION FLAGS: None detected\n"
            "REVIEWER VETO: Absolute contraindication — warfarin + NSAID at this "
            "dose in CKD3 patient; escalate to clinical pharmacist before any "
            "prescribing decision."
        )
        config = make_config(tmp_path)
        wf = DrugInteractionFlaggingWorkflow(
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
        assert "contraindication" in result.metadata["veto_reason"]
        assert result.metadata["vetoed"] is True
        assert result.metadata["first_draft"] == "initial draft"
        assert _VETO_BANNER in result.output

    async def test_no_veto_when_directive_is_none(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = DrugInteractionFlaggingWorkflow(
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
        wf = DrugInteractionFlaggingWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        for key in (
            "new_medication",
            "severity_flags",
            "evidence_flags",
            "contraindication_flags",
            "interaction_checklist",
            "disclaimer",
            "ledger_summary",
        ):
            assert key in result.metadata
        assert result.metadata["interaction_checklist"][0] == "[OWNER: Clinical Pharmacist]"


@pytest.mark.asyncio
class TestDisclaimer:
    async def test_disclaimer_in_output(self, tmp_path: Path) -> None:
        config = make_config(tmp_path)
        wf = DrugInteractionFlaggingWorkflow(
            executor=FakeExecutor(responses=[_GOOD_OUTPUT]),
            reviewer=FakeReviewer(results=[make_review(8.5, approved=True, critique=clean_critique())]),
            config=config,
            ledger=ClaimLedger(str(tmp_path / "ledger.json")),
            wiki=ResearchWiki(str(tmp_path / "wiki.json")),
        )
        result = await wf.run(request=make_request())
        assert _DISCLAIMER in result.output
