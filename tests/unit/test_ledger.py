"""Unit tests for src/core/ledger.py — no API calls."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from adv_multi_agent.core.ledger import Claim, ClaimLedger, ClaimStatus, Evidence


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_ledger(tmp_path: Path, filename: str = "ledger.json") -> ClaimLedger:
    return ClaimLedger(str(tmp_path / filename))


# ---------------------------------------------------------------------------
# add
# ---------------------------------------------------------------------------


class TestLedgerAdd:
    def test_returns_id(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        cid = ledger.add("Some claim text")
        assert isinstance(cid, str)
        assert len(cid) == 12

    def test_claim_is_pending(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        cid = ledger.add("claim")
        assert ledger.get(cid).status == ClaimStatus.PENDING

    def test_oversized_text_raises(self, tmp_path: Path) -> None:
        ledger = ClaimLedger(str(tmp_path / "l.json"), max_claim_chars=10)
        with pytest.raises(ValueError, match="claim text"):
            ledger.add("x" * 11)

    def test_persistence_across_instances(self, tmp_path: Path) -> None:
        path = str(tmp_path / "ledger.json")
        ledger1 = ClaimLedger(path)
        cid = ledger1.add("persisted claim", round_num=2)

        ledger2 = ClaimLedger(path)
        claim = ledger2.get(cid)
        assert claim.text == "persisted claim"
        assert claim.round_added == 2


# ---------------------------------------------------------------------------
# resolve / dispute / retract
# ---------------------------------------------------------------------------


class TestLedgerResolve:
    def test_resolve_to_supported(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        cid = ledger.add("claim")
        ledger.resolve(cid, ClaimStatus.SUPPORTED, round_num=1)
        assert ledger.get(cid).status == ClaimStatus.SUPPORTED
        assert ledger.get(cid).round_resolved == 1

    def test_resolve_to_pending_raises(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        cid = ledger.add("claim")
        with pytest.raises(ValueError, match="PENDING"):
            ledger.resolve(cid, ClaimStatus.PENDING, round_num=1)

    def test_resolve_unknown_id_raises(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        with pytest.raises(KeyError):
            ledger.resolve("nonexistent", ClaimStatus.SUPPORTED, round_num=1)

    def test_dispute(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        cid = ledger.add("claim")
        ledger.dispute(cid, round_num=2, critique="flawed")
        assert ledger.get(cid).status == ClaimStatus.DISPUTED

    def test_retract(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        cid = ledger.add("claim")
        ledger.retract(cid, round_num=3, reason="wrong")
        assert ledger.get(cid).status == ClaimStatus.RETRACTED


# ---------------------------------------------------------------------------
# attach_evidence
# ---------------------------------------------------------------------------


class TestAttachEvidence:
    def test_attach_happy(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        cid = ledger.add("claim")
        ev = Evidence(source="paper.pdf", excerpt="Quote here", page_or_line="p.5")
        ledger.attach_evidence(cid, ev)
        assert len(ledger.get(cid).evidence) == 1

    def test_attach_unknown_id_raises(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        with pytest.raises(KeyError):
            ledger.attach_evidence("bad", Evidence("src", "exc"))


# ---------------------------------------------------------------------------
# query methods
# ---------------------------------------------------------------------------


class TestLedgerQueries:
    def test_pending_filter(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        cid1 = ledger.add("pending claim")
        cid2 = ledger.add("will be resolved")
        ledger.resolve(cid2, ClaimStatus.SUPPORTED, round_num=1)

        pending = ledger.pending()
        assert len(pending) == 1
        assert pending[0].id == cid1

    def test_disputed_filter(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        cid = ledger.add("claim")
        ledger.dispute(cid, round_num=1, critique="bad")
        assert len(ledger.disputed()) == 1

    def test_summary_counts(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        cid1 = ledger.add("a")
        cid2 = ledger.add("b")
        ledger.resolve(cid1, ClaimStatus.SUPPORTED, round_num=1)
        ledger.dispute(cid2, round_num=1, critique="x")

        s = ledger.summary()
        assert s["pending"] == 0
        assert s["supported"] == 1
        assert s["disputed"] == 1
        assert s["total"] == 2

    def test_get_unknown_raises(self, tmp_path: Path) -> None:
        ledger = make_ledger(tmp_path)
        with pytest.raises(KeyError):
            ledger.get("missing")


# ---------------------------------------------------------------------------
# Claim.from_dict — resilience
# ---------------------------------------------------------------------------


class TestClaimFromDict:
    def test_unknown_keys_filtered(self) -> None:
        d = {"text": "claim", "unknown_field": "should be ignored"}
        c = Claim.from_dict(d)
        assert c.text == "claim"
        assert not hasattr(c, "unknown_field")

    def test_missing_fields_defaulted(self) -> None:
        c = Claim.from_dict({})
        assert c.text == ""
        assert c.status == ClaimStatus.PENDING

    def test_invalid_status_defaults_to_pending(self) -> None:
        c = Claim.from_dict({"status": "invalid_status_value"})
        assert c.status == ClaimStatus.PENDING

    def test_non_list_evidence_becomes_empty(self) -> None:
        c = Claim.from_dict({"evidence": "not a list"})
        assert c.evidence == []

    def test_evidence_dicts_parsed(self) -> None:
        d = {
            "evidence": [
                {"source": "paper", "excerpt": "text", "page_or_line": "p.1"}
            ]
        }
        c = Claim.from_dict(d)
        assert len(c.evidence) == 1
        assert c.evidence[0].source == "paper"


# ---------------------------------------------------------------------------
# _load — resilience
# ---------------------------------------------------------------------------


class TestLedgerLoad:
    def test_missing_file_starts_empty(self, tmp_path: Path) -> None:
        ledger = ClaimLedger(str(tmp_path / "nonexistent.json"))
        assert ledger.all() == []

    def test_empty_file_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        path.write_text("", encoding="utf-8")
        ledger = ClaimLedger(str(path))
        assert ledger.all() == []

    def test_corrupt_json_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        path.write_text("not valid json {{{{", encoding="utf-8")
        ledger = ClaimLedger(str(path))
        assert ledger.all() == []

    def test_m4_corrupt_json_emits_warning(self, tmp_path: Path) -> None:
        """M4: silent corrupt-load erased audit trail without trace."""
        import warnings
        path = tmp_path / "ledger.json"
        path.write_text("not valid json", encoding="utf-8")
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            ClaimLedger(str(path))
            assert any("load failed" in str(rec.message) for rec in w)

    def test_valid_json_wrong_shape_starts_empty(self, tmp_path: Path) -> None:
        path = tmp_path / "ledger.json"
        path.write_text(json.dumps([1, 2, 3]), encoding="utf-8")
        ledger = ClaimLedger(str(path))
        assert ledger.all() == []
