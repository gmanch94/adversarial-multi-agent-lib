"""Unit tests for core._internal.extract_flags — shared parser used by
recall, loyalty, and promo retail workflows.

Demand and labor workflows use a simpler inline parser by design (single
flag class, no sibling-header collisions), so they are NOT covered here.
"""
from __future__ import annotations

from adv_multi_agent.core._internal import extract_flags


class TestExtractFlagsBasic:
    def test_extracts_bullet_lines(self) -> None:
        critique = (
            "Overall score: 7/10\nKey issues: x\n"
            "SCOPE FLAGS:\n- Lot LOT-X missing\n- Store KRO-X missing\n"
            "EVIDENCE FLAGS: None detected\nREVIEWER VETO: None"
        )
        flags = extract_flags(critique, "SCOPE FLAGS:")
        assert len(flags) == 2
        assert any("LOT-X" in f for f in flags)

    def test_returns_empty_for_none_detected(self) -> None:
        assert extract_flags("SCOPE FLAGS: None detected", "SCOPE FLAGS:") == []

    def test_returns_empty_when_header_absent(self) -> None:
        assert extract_flags("clean.", "SCOPE FLAGS:") == []

    def test_returns_empty_for_none_variant(self) -> None:
        # "None" and "n/a" are also recognised empty markers.
        assert extract_flags("MARGIN FLAGS: None", "MARGIN FLAGS:") == []
        assert extract_flags("MARGIN FLAGS: n/a", "MARGIN FLAGS:") == []


class TestExtractFlagsSectionStop:
    def test_stops_at_overall_header(self) -> None:
        critique = (
            "TIMING FLAGS:\n- Memorial Day overlap inflates lift\n"
            "Overall score: 7/10"
        )
        flags = extract_flags(critique, "TIMING FLAGS:")
        assert len(flags) == 1

    def test_stops_at_inline_uppercase_header_on_same_line(self) -> None:
        # "EVIDENCE FLAGS: None detected" must terminate SCOPE FLAGS parsing
        # rather than be swallowed as a flag.
        critique = (
            "SCOPE FLAGS:\n- Lot missing\n"
            "EVIDENCE FLAGS: None detected\nREVIEWER VETO: ..."
        )
        flags = extract_flags(critique, "SCOPE FLAGS:")
        assert len(flags) == 1
        assert "Lot missing" in flags[0]

    def test_stops_at_inline_reviewer_veto_header(self) -> None:
        critique = (
            "EVIDENCE FLAGS:\n- No primary lab evidence\n"
            "REVIEWER VETO: directive text"
        )
        flags = extract_flags(critique, "EVIDENCE FLAGS:")
        assert len(flags) == 1

    def test_stops_at_markdown_heading(self) -> None:
        critique = "FAIRNESS FLAGS:\n- proxy detected\n# Next section\n- not a flag"
        flags = extract_flags(critique, "FAIRNESS FLAGS:")
        assert len(flags) == 1


class TestExtractFlagsBulletNormalisation:
    def test_strips_bullet_prefix(self) -> None:
        critique = "MARGIN FLAGS:\n* item 1\n• item 2\n- item 3"
        flags = extract_flags(critique, "MARGIN FLAGS:")
        assert flags == ["item 1", "item 2", "item 3"]

    def test_does_not_misread_hyphenated_text_as_header(self) -> None:
        # A bullet line "- Lot LOT-X: missing" has a colon but the LHS
        # ("- Lot LOT-X") is not uppercase-only-with-spaces, so it must
        # NOT be treated as a section header.
        critique = "SCOPE FLAGS:\n- Lot LOT-X: missing"
        flags = extract_flags(critique, "SCOPE FLAGS:")
        assert len(flags) == 1
        assert "LOT-X" in flags[0]

    def test_ignores_blank_lines(self) -> None:
        critique = "TIMING FLAGS:\n\n- only flag\n\nOverall score: 7"
        flags = extract_flags(critique, "TIMING FLAGS:")
        assert flags == ["only flag"]


class TestExtractFlagsHeaderAnchoring:
    """Regression coverage for M1 (substring-containment header match).

    A commentary mention of the header name earlier in the critique must
    NOT mis-anchor the parser. The real flag section begins at a
    line-anchored occurrence.
    """

    def test_commentary_mention_does_not_mis_anchor(self) -> None:
        critique = (
            "Mentioning SCOPE FLAGS: should be tightened in the next revision.\n"
            "Some prose here.\n"
            "SCOPE FLAGS:\n"
            "- real flag from the actual section\n"
            "Overall score: 7"
        )
        flags = extract_flags(critique, "SCOPE FLAGS:")
        # Without anchoring, the parser would mis-anchor on the first
        # mention and return ["should be tightened in the next revision."]
        # or trip over later sibling-header handling.
        assert flags == ["real flag from the actual section"]

    def test_indented_header_still_matches(self) -> None:
        # Leading whitespace before the header is allowed.
        critique = "  SCOPE FLAGS:\n- a flag"
        flags = extract_flags(critique, "SCOPE FLAGS:")
        assert flags == ["a flag"]

    def test_header_not_at_line_start_returns_empty_when_no_real_section(
        self,
    ) -> None:
        # If the header is only mentioned inline (never at line-start), no
        # real section exists — return [].
        critique = "Some line mentions SCOPE FLAGS: inline only.\nOverall score: 8"
        flags = extract_flags(critique, "SCOPE FLAGS:")
        assert flags == []


class TestExtractFlagsSizeCap:
    """Regression coverage for L2 — defence-in-depth cap on returned flag
    count. Prevents a pathological reviewer output from ballooning the
    next-round executor prompt via re-injection in `_format_flag_section`."""

    def test_returns_at_most_max_flags(self) -> None:
        from adv_multi_agent.core._internal import _MAX_FLAGS_PER_HEADER

        bullets = "\n".join(f"- flag {i}" for i in range(_MAX_FLAGS_PER_HEADER + 50))
        critique = f"SCOPE FLAGS:\n{bullets}\nOverall score: 7"
        flags = extract_flags(critique, "SCOPE FLAGS:")
        assert len(flags) == _MAX_FLAGS_PER_HEADER
        # First N preserved in order.
        assert flags[0] == "flag 0"
        assert flags[-1] == f"flag {_MAX_FLAGS_PER_HEADER - 1}"
