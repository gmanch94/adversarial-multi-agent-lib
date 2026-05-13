"""Unit tests for src/core/wiki.py — no API calls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from adv_multi_agent.core.wiki import EntryKind, ResearchWiki, WikiEntry


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_wiki(tmp_path: Path, filename: str = "wiki.json") -> ResearchWiki:
    return ResearchWiki(str(tmp_path / filename))


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


class TestWikiAdd:
    def test_returns_id(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        eid = wiki.add(EntryKind.NOTE, title="t", body="b")
        assert isinstance(eid, str)
        assert len(eid) == 12

    def test_oversized_body_raises(self, tmp_path: Path) -> None:
        wiki = ResearchWiki(str(tmp_path / "w.json"), max_body_chars=10)
        with pytest.raises(ValueError, match="body"):
            wiki.add(EntryKind.NOTE, title="t", body="x" * 11)

    def test_unknown_supersedes_raises(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        with pytest.raises(ValueError, match="supersedes"):
            wiki.add(EntryKind.NOTE, title="t", body="b", supersedes="nonexistent")

    def test_persistence_across_instances(self, tmp_path: Path) -> None:
        path = str(tmp_path / "wiki.json")
        wiki1 = ResearchWiki(path)
        eid = wiki1.add(EntryKind.HYPOTHESIS, title="H1", body="some idea", round_num=1)

        wiki2 = ResearchWiki(path)
        entry = wiki2.get(eid)
        assert entry.title == "H1"
        assert entry.kind == EntryKind.HYPOTHESIS
        assert entry.round_num == 1

    def test_valid_supersedes_accepted(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        eid1 = wiki.add(EntryKind.NOTE, title="old", body="v1")
        eid2 = wiki.add(EntryKind.NOTE, title="new", body="v2", supersedes=eid1)
        assert wiki.get(eid2).supersedes == eid1


# ---------------------------------------------------------------------------
# context_for_round — security invariants
# ---------------------------------------------------------------------------


class TestContextForRound:
    def test_improvement_excluded(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        wiki.add(EntryKind.IMPROVEMENT, title="improve me", body="change X", round_num=1)
        wiki.add(EntryKind.NOTE, title="normal", body="keep this", round_num=1)

        ctx = wiki.context_for_round(round_num=2)
        assert "improve me" not in ctx
        assert "keep this" in ctx

    def test_round_filter(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        wiki.add(EntryKind.NOTE, title="round1", body="early", round_num=1)
        wiki.add(EntryKind.NOTE, title="round3", body="late", round_num=3)

        ctx = wiki.context_for_round(round_num=2)
        assert "round1" in ctx
        assert "round3" not in ctx

    def test_fenced_delimiters_present(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        wiki.add(EntryKind.NOTE, title="note", body="content", round_num=1)

        ctx = wiki.context_for_round(round_num=1)
        assert "<<WIKI_ENTRY" in ctx
        assert "<<END_WIKI_ENTRY>>" in ctx

    def test_control_chars_stripped(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        wiki.add(EntryKind.NOTE, title="t", body="hello\x00world\x1fend", round_num=1)

        ctx = wiki.context_for_round(round_num=1)
        assert "\x00" not in ctx
        assert "\x1f" not in ctx
        assert "hello" in ctx

    def test_total_char_budget_enforced(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        for i in range(20):
            wiki.add(EntryKind.NOTE, title=f"entry{i}", body="x" * 300, round_num=1)

        ctx = wiki.context_for_round(round_num=1, max_total_chars=500)
        assert len(ctx) <= 600  # budget + small overhead for final chunk

    def test_empty_wiki_returns_empty_string(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        assert wiki.context_for_round(round_num=1) == ""


# ---------------------------------------------------------------------------
# approve / reject improvement
# ---------------------------------------------------------------------------


class TestImprovementApproval:
    def test_approve_sets_approved_true(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        eid = wiki.add_improvement("do something", round_num=1)
        wiki.approve_improvement(eid)
        assert wiki.get(eid).approved is True

    def test_reject_sets_approved_false(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        eid = wiki.add_improvement("do something", round_num=1)
        wiki.reject_improvement(eid)
        assert wiki.get(eid).approved is False

    def test_approve_non_improvement_raises(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        eid = wiki.add(EntryKind.NOTE, title="note", body="body")
        with pytest.raises(ValueError, match="not an improvement"):
            wiki.approve_improvement(eid)

    def test_pending_improvements_only_unset(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        eid1 = wiki.add_improvement("prop A", round_num=1)
        eid2 = wiki.add_improvement("prop B", round_num=1)
        wiki.approve_improvement(eid1)

        pending = wiki.pending_improvements()
        assert len(pending) == 1
        assert pending[0].id == eid2

    def test_approved_improvements_list(self, tmp_path: Path) -> None:
        wiki = make_wiki(tmp_path)
        eid = wiki.add_improvement("prop", round_num=1)
        wiki.approve_improvement(eid)
        approved = wiki.approved_improvements()
        assert len(approved) == 1
        assert approved[0].id == eid


# ---------------------------------------------------------------------------
# WikiEntry.from_dict — resilience
# ---------------------------------------------------------------------------


class TestWikiEntryFromDict:
    def test_unknown_keys_ignored(self) -> None:
        e = WikiEntry.from_dict({"title": "t", "extra_field": "x"})
        assert e.title == "t"
        assert not hasattr(e, "extra_field")

    def test_missing_fields_defaulted(self) -> None:
        e = WikiEntry.from_dict({})
        assert e.kind == EntryKind.NOTE
        assert e.title == ""
        assert e.body == ""

    def test_invalid_kind_defaults_to_note(self) -> None:
        e = WikiEntry.from_dict({"kind": "invalid_kind_value"})
        assert e.kind == EntryKind.NOTE

    def test_non_list_tags_becomes_empty(self) -> None:
        e = WikiEntry.from_dict({"tags": "not-a-list"})
        assert e.tags == []

    def test_list_tags_preserved(self) -> None:
        e = WikiEntry.from_dict({"tags": ["a", "b"]})
        assert e.tags == ["a", "b"]


# ---------------------------------------------------------------------------
# _load — resilience
# ---------------------------------------------------------------------------


class TestWikiLoad:
    def test_missing_file_starts_empty(self, tmp_path: Path) -> None:
        wiki = ResearchWiki(str(tmp_path / "nonexistent.json"))
        assert wiki.all() == []

    def test_empty_file_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "wiki.json"
        path.write_text("", encoding="utf-8")
        wiki = ResearchWiki(str(path))
        assert wiki.all() == []

    def test_corrupt_json_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "wiki.json"
        path.write_text("not valid json {{{{", encoding="utf-8")
        wiki = ResearchWiki(str(path))
        assert wiki.all() == []

    def test_valid_json_wrong_shape_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "wiki.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        wiki = ResearchWiki(str(path))
        assert wiki.all() == []
