"""Regression tests for the A11 security-audit parser fixes (2026-07-23).

Each test below reproduces a failure shape the audit demonstrated empirically
against the pre-fix parser. They are grouped by audit finding id.

The distinction that governs severity throughout: a parser that UNDER-collects
is **fail-open** — the convergence gate clause `and not <flags>` is satisfied,
so that safety class is silently unenforced and the workflow converges. A
parser that OVER-collects is **fail-safe** — extra flags block convergence and
cost a round. Every fix here trades fail-open for fail-safe, never the reverse.
"""
from __future__ import annotations

import pytest

from adv_multi_agent.core._internal import (
    extract_flags,
    extract_veto_directive,
    missing_flag_headers,
    sanitize_for_prompt,
)
from adv_multi_agent.core.wiki import ResearchWiki

_H = "SCOPE FLAGS:"
_FLAG = "lot range too narrow"


class TestA11M1HeaderFormatTolerance:
    """A11-M1 — reviewer formatting deviations must not empty a flag class."""

    @pytest.mark.parametrize(
        "critique",
        [
            pytest.param(f"**SCOPE FLAGS:**\n- {_FLAG}\n", id="markdown-bold"),
            pytest.param(f"**SCOPE FLAGS**:\n- {_FLAG}\n", id="bold-colon-outside"),
            pytest.param(f"SCOPE FLAGS :\n- {_FLAG}\n", id="space-before-colon"),
            pytest.param(f"1. SCOPE FLAGS:\n- {_FLAG}\n", id="numbered"),
            pytest.param(f"1) SCOPE FLAGS:\n- {_FLAG}\n", id="numbered-paren"),
            pytest.param(f"- SCOPE FLAGS:\n- {_FLAG}\n", id="bulleted"),
            pytest.param(f"Scope flags:\n- {_FLAG}\n", id="lowercase"),
            pytest.param(f"   SCOPE FLAGS:\n   - {_FLAG}\n", id="indented"),
        ],
    )
    def test_deviation_still_extracts(self, critique: str) -> None:
        assert extract_flags(critique, _H) == [_FLAG]


class TestA11M1MissingHeaderIsDistinguishable:
    """A11-M1 root — absence must be separable from 'None detected'."""

    def test_absent_header_reported_missing(self) -> None:
        critique = "Overall score: 9/10\nKey issues: none\n"
        assert extract_flags(critique, _H) == []
        assert missing_flag_headers(critique, [_H]) == [_H]

    def test_emitted_empty_header_not_reported_missing(self) -> None:
        critique = "SCOPE FLAGS: None detected\n"
        assert extract_flags(critique, _H) == []
        assert missing_flag_headers(critique, [_H]) == []

    def test_partial_emission_reports_only_the_absent_one(self) -> None:
        critique = "SCOPE FLAGS: None detected\nOverall score: 9/10\n"
        assert missing_flag_headers(critique, [_H, "EVIDENCE FLAGS:"]) == [
            "EVIDENCE FLAGS:"
        ]

    def test_missing_detection_shares_the_tolerant_anchor(self) -> None:
        assert missing_flag_headers("**SCOPE FLAGS:** None detected\n", [_H]) == []


class TestA11M4LastMatchWins:
    """A11-M4 — an earlier quoted no-flag/no-veto line must not shadow the real one."""

    def test_earlier_empty_marker_does_not_shadow_real_section(self) -> None:
        critique = f"SCOPE FLAGS: None detected\nSCOPE FLAGS:\n- {_FLAG}\n"
        assert extract_flags(critique, _H) == [_FLAG]

    def test_earlier_none_veto_does_not_suppress_real_veto(self) -> None:
        critique = (
            "REVIEWER VETO: None\n"
            "SCOPE FLAGS:\n- x\n"
            "REVIEWER VETO: Halt, expand the recall.\n"
        )
        assert extract_veto_directive(critique) == "Halt, expand the recall."


class TestA11M5VetoMarkerTolerance:
    """A11-M5 — a genuine halt directive must survive formatting variance."""

    @pytest.mark.parametrize(
        "critique",
        [
            pytest.param("**REVIEWER VETO:** halt now\n", id="bold"),
            pytest.param("- REVIEWER VETO: halt now\n", id="bulleted"),
            pytest.param("1. REVIEWER VETO: halt now\n", id="numbered"),
            pytest.param("REVIEWER VETO : halt now\n", id="space-before-colon"),
        ],
    )
    def test_deviation_still_extracts(self, critique: str) -> None:
        assert extract_veto_directive(critique) == "halt now"

    def test_continuation_beginning_overall_is_kept(self) -> None:
        critique = "REVIEWER VETO:\nOverall this product must be recalled now\n"
        assert extract_veto_directive(critique) == (
            "Overall this product must be recalled now"
        )

    def test_none_with_trailing_period_is_still_no_veto(self) -> None:
        assert extract_veto_directive("REVIEWER VETO: None.\n") is None

    @pytest.mark.parametrize("token", ["None", "none detected", "N/A"])
    def test_no_veto_tokens(self, token: str) -> None:
        assert extract_veto_directive(f"REVIEWER VETO: {token}\n") is None


class TestA11L2VetoContinuationLines:
    """A11-L2 — continuation lines were dropped whenever the marker line had text."""

    def test_continuation_after_text_on_marker_line(self) -> None:
        critique = "REVIEWER VETO: Halt.\nExpand to lot 42.\nNotify the regulator.\n"
        assert extract_veto_directive(critique) == (
            "Halt. Expand to lot 42. Notify the regulator."
        )

    def test_continuation_with_empty_marker_line_unchanged(self) -> None:
        critique = "REVIEWER VETO:\nHalt.\nSerious unexpected ADR.\n"
        assert extract_veto_directive(critique) == "Halt. Serious unexpected ADR."

    def test_sibling_header_still_terminates(self) -> None:
        critique = "REVIEWER VETO: Halt.\nSCOPE FLAGS:\n- unrelated\n"
        assert extract_veto_directive(critique) == "Halt."


class TestA11L3EmptyMarkerMidSection:
    """A11-L3 — a `none` bullet after real flags must not discard them."""

    def test_mid_section_none_keeps_prior_flags(self) -> None:
        critique = f"SCOPE FLAGS:\n- {_FLAG}\n- distributor list incomplete\n- None\n"
        assert extract_flags(critique, _H) == [_FLAG, "distributor list incomplete"]

    def test_leading_none_still_means_empty(self) -> None:
        assert extract_flags("SCOPE FLAGS:\n- None detected\n", _H) == []


class TestA11L4ProseTerminator:
    """A11-L4 — only the two real terminator lines may end a section."""

    def test_bulleted_flag_beginning_overall_is_collected(self) -> None:
        critique = (
            "SCOPE FLAGS:\n"
            "- Overall recall breadth is understated for lot 42\n"
            "- second real flag\n"
        )
        assert extract_flags(critique, _H) == [
            "Overall recall breadth is understated for lot 42",
            "second real flag",
        ]

    def test_overall_score_line_still_terminates(self) -> None:
        critique = f"SCOPE FLAGS:\n- {_FLAG}\nOverall score: 9/10\n"
        assert extract_flags(critique, _H) == [_FLAG]

    def test_key_issues_line_still_terminates(self) -> None:
        critique = f"SCOPE FLAGS:\n- {_FLAG}\nKey issues: something\n"
        assert extract_flags(critique, _H) == [_FLAG]


class TestA11L5FlatLabelledFlags:
    """A11-L5 — `CAPS: value` flags vs a genuine sibling section header."""

    def test_flat_labelled_flags_are_collected(self) -> None:
        critique = (
            "SCOPE FLAGS:\n"
            "LOT RANGE: too narrow, extend to 2024-08\n"
            "DISTRIBUTOR LIST: incomplete\n"
        )
        assert extract_flags(critique, _H) == [
            "LOT RANGE: too narrow, extend to 2024-08",
            "DISTRIBUTOR LIST: incomplete",
        ]

    def test_sibling_after_a_bulleted_flag_terminates(self) -> None:
        critique = (
            "SCOPE FLAGS:\n- One market omits the warning\n"
            "RECOMMENDATION: align the local label\n"
        )
        assert extract_flags(critique, _H) == ["One market omits the warning"]

    def test_flags_sibling_terminates_even_without_a_bullet(self) -> None:
        critique = "SCOPE FLAGS:\nEVIDENCE FLAGS: None detected\n"
        assert extract_flags(critique, _H) == []

    def test_bare_header_sibling_terminates_even_without_a_bullet(self) -> None:
        critique = f"SCOPE FLAGS:\n- {_FLAG}\nRECOMMENDATION:\n"
        assert extract_flags(critique, _H) == [_FLAG]


class TestA11M3SanitizeNeverExceedsBudget:
    """A11-M3 — the live crash: sanitize returned max_chars + 14."""

    @pytest.mark.parametrize("cap", [1, 5, 14, 15, 100, 8000])
    def test_never_exceeds_max_chars(self, cap: int) -> None:
        assert len(sanitize_for_prompt("x" * 20_000, max_chars=cap)) <= cap

    def test_marker_retained_when_it_fits(self) -> None:
        assert sanitize_for_prompt("x" * 9000, max_chars=8000).endswith(
            "...[truncated]"
        )

    def test_wiki_add_feedback_accepts_a_sanitized_oversized_critique(
        self, tmp_path
    ) -> None:
        """The exact 60-call-site pattern that used to raise out of run()."""
        cap = 8000
        wiki = ResearchWiki(str(tmp_path / "wiki.json"), max_body_chars=cap)
        wiki.add_feedback(
            sanitize_for_prompt("x" * 9000, max_chars=cap), round_num=1, score=9.0
        )
        assert len(wiki.all()) == 1


class TestA11M8VetoDirectiveIsSanitized:
    """A11-M8 — veto_reason is rendered verbatim into operator-facing output."""

    def test_control_characters_stripped(self) -> None:
        veto = extract_veto_directive("REVIEWER VETO: halt \x1b[2J\x07 now\n")
        assert veto is not None
        assert "\x1b" not in veto and "\x07" not in veto

    def test_bounded_by_max_chars(self) -> None:
        veto = extract_veto_directive(
            "REVIEWER VETO: " + "y" * 5000 + "\n", max_chars=200
        )
        assert veto is not None
        assert len(veto) <= 200


class TestA11M7PerFlagLengthCap:
    """A11-M7 — a single flag reached metadata at full critique length."""

    def test_flag_text_is_bounded(self) -> None:
        flags = extract_flags(f"SCOPE FLAGS:\n- {'z' * 5000}\n", _H)
        assert len(flags) == 1
        assert len(flags[0]) <= 500
