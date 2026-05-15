"""Unit tests for core._internal.extract_veto_directive — shared veto parser
used by every reviewer-veto workflow (recall_scope + the 4 PC veto workflows).

Covers:
- M-PC-1 regression: a commentary mention of `REVIEWER VETO:` earlier in the
  critique (e.g. a reviewer quoting the criteria block back) must NOT
  mis-anchor the parser to the substring occurrence.
- M2 regression: marker on line 1 + continuation directive on subsequent
  lines is captured as the directive (no early return on first-line "none").
- L5 regression: sibling-header stop uses the alpha+spaces uppercase rule
  (not the looser `[:-1].isupper()`).
- Conventional no-veto returns + multi-line directive + truncation cap.
"""
from __future__ import annotations

from adv_multi_agent.core._internal import extract_veto_directive


class TestExtractVetoDirectiveBasic:
    def test_returns_none_when_marker_absent(self) -> None:
        assert extract_veto_directive("clean review", "REVIEWER VETO:", 1000) is None

    def test_returns_none_when_directive_is_none(self) -> None:
        assert (
            extract_veto_directive("REVIEWER VETO: None", "REVIEWER VETO:", 1000)
            is None
        )

    def test_returns_none_when_directive_is_none_detected(self) -> None:
        assert (
            extract_veto_directive(
                "REVIEWER VETO: none detected", "REVIEWER VETO:", 1000
            )
            is None
        )

    def test_returns_none_when_directive_is_n_a(self) -> None:
        assert (
            extract_veto_directive("REVIEWER VETO: n/a", "REVIEWER VETO:", 1000)
            is None
        )

    def test_returns_directive_on_same_line(self) -> None:
        veto = extract_veto_directive(
            "REVIEWER VETO: escalate immediately, life-safety risk",
            "REVIEWER VETO:",
            1000,
        )
        assert veto is not None
        assert "escalate immediately" in veto

    def test_returns_directive_on_continuation_lines(self) -> None:
        critique = (
            "REVIEWER VETO:\n"
            "Life-safety pathogen with no regulator contact.\n"
            "Escalate to safety officer."
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto is not None
        assert "Life-safety" in veto
        assert "Escalate" in veto

    def test_truncates_to_max_chars(self) -> None:
        critique = "REVIEWER VETO: " + "x" * 5000
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 200)
        assert veto is not None
        assert len(veto) == 200


class TestExtractVetoDirectiveM2:
    """M2 — marker on first line, continuation directive after."""

    def test_marker_on_first_line_then_continuation_directive(self) -> None:
        critique = (
            "REVIEWER VETO: none detected\n"
            "Wait — on reflection, escalate to safety officer."
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto is not None
        assert "escalate" in veto.lower()
        assert "safety officer" in veto.lower()

    def test_marker_only_returns_none(self) -> None:
        assert (
            extract_veto_directive(
                "REVIEWER VETO: none detected", "REVIEWER VETO:", 1000
            )
            is None
        )


class TestExtractVetoDirectiveL5:
    """L5 — sibling-header check rule consistency with extract_flags."""

    def test_sibling_header_check_rejects_digit_only_colon_line(self) -> None:
        """A line like `1234:` is NOT a section header — should be captured."""
        critique = (
            "REVIEWER VETO:\n"
            "Halt — see incident\n"
            "1234:\n"
            "additional directive text"
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto is not None
        assert "Halt" in veto
        assert "1234:" in veto
        assert "additional directive" in veto

    def test_sibling_header_check_still_stops_on_real_header(self) -> None:
        critique = (
            "REVIEWER VETO:\n"
            "Real directive line\n"
            "EVIDENCE FLAGS:\n"
            "- not part of veto"
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto is not None
        assert "Real directive" in veto
        assert "EVIDENCE" not in veto
        assert "not part of veto" not in veto

    def test_sibling_header_check_stops_on_hyphenated_header(self) -> None:
        """H-IND-1: hyphenated peer headers (DESIGN-DEFECT FLAGS, etc.) must
        also terminate the veto continuation parse. Prior to the H-IND-1 fix,
        `lhs.replace(' ', '').isalpha()` rejected hyphens, so hyphenated
        sibling headers were captured as veto-continuation text."""
        critique = (
            "REVIEWER VETO:\n"
            "Real directive line\n"
            "DESIGN-DEFECT FLAGS:\n"
            "- not part of veto"
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto is not None
        assert "Real directive" in veto
        assert "DESIGN-DEFECT" not in veto
        assert "not part of veto" not in veto


class TestExtractVetoDirectiveMPC1:
    """M-PC-1 regression — line-anchored marker match.

    Substring containment in commentary (e.g. a reviewer quoting the criteria
    block back in prose) must NOT mis-anchor the parser. The line-anchored
    regex requires the marker to appear at line-start (allowing leading
    whitespace).
    """

    def test_substring_in_commentary_does_not_mis_anchor(self) -> None:
        """A reviewer that quotes `REVIEWER VETO:` mid-prose must not anchor
        the parser there. The line-anchored regex skips mid-line occurrences
        and finds the real terminal `REVIEWER VETO: None` line."""
        critique = (
            "Per the REVIEWER VETO: criteria above, I evaluated the "
            "life-safety signal but found no triggering condition.\n"
            "\n"
            "Overall score: 9.0/10\n"
            "Key issues: None.\n"
            "RESERVE FLAGS: None detected\n"
            "PRECEDENT FLAGS: None detected\n"
            "LITIGATION FLAGS: None detected\n"
            "REVIEWER VETO: None"
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        # Without line-anchoring, the OLD parser would have anchored on
        # the mid-prose substring and returned " criteria above, I evaluated..."
        # as the veto directive. With M-PC-1 hardening, it must skip the
        # in-prose mention and read the actual line-anchored `None`.
        assert veto is None

    def test_substring_in_commentary_then_real_veto(self) -> None:
        """Same scenario but the real terminal marker carries a real
        directive — must be captured, not the prose substring."""
        critique = (
            "I noted the REVIEWER VETO: requirement and applied it.\n"
            "\n"
            "RESERVE FLAGS: None detected\n"
            "REVIEWER VETO: Catastrophic-injury signal with under-reserved "
            "indemnity; escalate to senior actuary."
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto is not None
        assert "Catastrophic" in veto
        assert "senior actuary" in veto
        # NOT the commentary substring:
        assert "noted the" not in veto
        assert "requirement and applied it" not in veto

    def test_indented_marker_still_matches(self) -> None:
        """Leading whitespace before the marker is permitted (the regex
        allows `\\s*` before the marker)."""
        critique = "  REVIEWER VETO: Indented directive"
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto is not None
        assert "Indented directive" in veto

    def test_marker_mid_line_only_returns_none(self) -> None:
        """If the marker only appears mid-prose and never at line-start,
        no real veto exists."""
        critique = (
            "I considered the REVIEWER VETO: criterion but found nothing.\n"
            "Overall score: 8.5/10"
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto is None


class TestExtractVetoDirectiveSectionStop:
    """The continuation-line stop list (`overall`, `key issues`, `#`,
    sibling-header) breaks the multi-line collection."""

    def test_stops_at_overall_continuation(self) -> None:
        critique = (
            "REVIEWER VETO:\n"
            "Real directive\n"
            "Overall score: 9.0/10"
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto == "Real directive"

    def test_stops_at_markdown_header_continuation(self) -> None:
        critique = (
            "REVIEWER VETO:\n"
            "Real directive\n"
            "# Next section\n"
            "more text"
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto == "Real directive"

    def test_blank_line_after_directive_breaks(self) -> None:
        critique = (
            "REVIEWER VETO:\n"
            "Real directive\n"
            "\n"
            "Some other prose"
        )
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto == "Real directive"

    def test_bullet_prefix_stripped(self) -> None:
        critique = "REVIEWER VETO:\n- bulleted directive"
        veto = extract_veto_directive(critique, "REVIEWER VETO:", 1000)
        assert veto == "bulleted directive"


class TestExtractVetoDirectiveCustomMarker:
    """The marker argument is parameterised — verify a different marker
    works (defence-in-depth for future veto-using workflows)."""

    def test_custom_marker(self) -> None:
        critique = "SAFETY VETO: halt operations immediately"
        veto = extract_veto_directive(critique, "SAFETY VETO:", 1000)
        assert veto == "halt operations immediately"

    def test_custom_marker_with_none(self) -> None:
        assert (
            extract_veto_directive("SAFETY VETO: None", "SAFETY VETO:", 1000)
            is None
        )

    def test_custom_marker_regex_escaped(self) -> None:
        """Marker containing regex metacharacters must be escaped — verify
        that `re.escape` is correctly applied inside the helper."""
        critique = "VETO (CRITICAL): halt"
        veto = extract_veto_directive(critique, "VETO (CRITICAL):", 1000)
        assert veto == "halt"
