"""Tier 3.1 audit-ledger tests — pure chain/anchor verification logic.

These exercise the security-critical parts (hash-chain integrity, the C1
all-anchors truncate-and-re-anchor catch, the H2 no-false-positive property,
outbox-gap detection) WITHOUT a DB — they operate on fabricated column-dicts
built with the same canonicalization the sink uses. A live-Postgres integration
test would additionally exercise RLS + grants (needs_postgres); the chain logic
is what's worth pinning here.

Design: docs/superpowers/specs/2026-07-23-durable-audit-log-design.md.
"""
from __future__ import annotations

from typing import Any

from examples.production.durable_postgres.audit_sink import (
    GENESIS_PREV_HASH,
    audit_hash_input,
    canonical_extra,
    row_hash_of,
)
from examples.production.durable_postgres.scripts.reconcile_audit import (
    find_terminal_gaps,
)
from examples.production.durable_postgres.scripts.verify_audit_chain import (
    verify_against_anchors,
    verify_chain,
)


def _row(seq: int, prev_hash: str, *, event_seq: int, run_id: str = "run1",
         event_type: str = "round_completed", round_: int = 1,
         at: str = "2026-07-23T00:00:00+00:00", extra: dict[str, Any] | None = None,
         content_hash: str = "a" * 64, tenant_id: str = "t1") -> dict[str, Any]:
    extra_canonical = canonical_extra(extra or {})
    hi = audit_hash_input(
        tenant_id=tenant_id, seq=seq, run_id=run_id, event_type=event_type,
        event_seq=event_seq, round_=round_, at=at, workflow_class="pkg.Wf",
        workflow_version_hash=None, executor_model="claude-opus-4-7",
        reviewer_model="gpt-4o", content_hash=content_hash,
        extra_canonical=extra_canonical, prev_hash=prev_hash,
    )
    return {
        "tenant_id": tenant_id, "seq": seq, "run_id": run_id, "event_type": event_type,
        "event_seq": event_seq, "round": round_, "at": at, "workflow_class": "pkg.Wf",
        "workflow_version_hash": None, "executor_model": "claude-opus-4-7",
        "reviewer_model": "gpt-4o", "content_hash": content_hash,
        "extra_canonical": extra_canonical, "prev_hash": prev_hash,
        "hash_input": hi, "row_hash": row_hash_of(hi),
    }


def _chain(n: int) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    prev = GENESIS_PREV_HASH
    for i in range(1, n + 1):
        r = _row(i, prev, event_seq=i)
        rows.append(r)
        prev = r["row_hash"]
    return rows


# ---------------- canonicalization ----------------


def test_canonical_extra_key_order_insensitive():
    assert canonical_extra({"score": 1, "converged": True}) == canonical_extra(
        {"converged": True, "score": 1}
    )


def test_hash_input_deterministic():
    kw = dict(tenant_id="t1", seq=1, run_id="r", event_type="veto", event_seq=1,
              round_=2, at="x", workflow_class="c", workflow_version_hash=None,
              executor_model="e", reviewer_model="rv", content_hash="a" * 64,
              extra_canonical="{}", prev_hash=GENESIS_PREV_HASH)
    assert audit_hash_input(**kw) == audit_hash_input(**kw)


# ---------------- verify_chain ----------------


def test_clean_chain_verifies():
    assert verify_chain(_chain(3)) == []


def test_h2_no_false_positive_with_float_extra_and_tz_at():
    """Review H2: a row with a float in extra + a tz-offset `at` must verify
    clean (hash bound to app-owned TEXT, not a normalizing DB column)."""
    row = _row(1, GENESIS_PREV_HASH, event_seq=1,
               extra={"score": 0.123456789, "converged": False},
               at="2026-07-23T09:30:00.123456+05:30")
    assert verify_chain([row]) == []


def test_detect_edited_row_hash():
    rows = _chain(3)
    rows[1] = {**rows[1], "row_hash": "f" * 64}
    errs = verify_chain(rows)
    assert any("row_hash tampered" in e for e in errs)


def test_detect_edited_column_breaks_hash_input_match():
    rows = _chain(2)
    rows[0] = {**rows[0], "content_hash": "b" * 64}  # column edited, hash_input stale
    errs = verify_chain(rows)
    assert any("disagrees with typed columns" in e for e in errs)


def test_detect_deleted_middle_row():
    rows = _chain(3)
    del rows[1]  # drop seq=2
    errs = verify_chain(rows)
    assert errs  # seq gap + prev_hash break
    assert any("gap/reorder" in e or "chain link" in e for e in errs)


def test_detect_reordered_rows():
    rows = _chain(3)
    rows[0], rows[1] = rows[1], rows[0]
    assert verify_chain(rows) != []


# ---------------- verify_against_anchors (C1 / D-AUDIT-8) ----------------


def test_anchor_clean():
    rows = _chain(3)
    anchors = [{"seq": 3, "row_hash": rows[2]["row_hash"], "created_at": "2026-07-23T01:00:00"}]
    assert verify_against_anchors(rows, anchors) == []


def test_anchor_catches_truncate_and_reanchor():
    """C1: the whole point. Attacker truncates the chain and PUTs a fresh anchor
    at the cut. The earlier immutable anchor (seq=3) still exists in the WORM
    store and no longer matches the (shortened) live chain."""
    full = _chain(3)
    legit_anchor = {"seq": 3, "row_hash": full[2]["row_hash"], "created_at": "2026-07-23T01:00:00"}
    # Attacker's world: live chain truncated to seq 1..2, forged later anchor at seq=2.
    live = full[:2]
    forged_anchor = {"seq": 2, "row_hash": live[1]["row_hash"], "created_at": "2026-07-23T05:00:00"}
    errs = verify_against_anchors(live, [legit_anchor, forged_anchor])
    assert any("truncation" in e for e in errs)


def test_anchor_conflict_is_tamper():
    rows = _chain(2)
    anchors = [
        {"seq": 2, "row_hash": rows[1]["row_hash"], "created_at": "2026-07-23T01:00:00"},
        {"seq": 2, "row_hash": "c" * 64, "created_at": "2026-07-23T02:00:00"},
    ]
    assert any("anchor conflict" in e for e in verify_against_anchors(rows, anchors))


def test_anchor_post_rewrite_detected():
    rows = _chain(2)
    anchors = [{"seq": 2, "row_hash": "d" * 64, "created_at": "2026-07-23T01:00:00"}]  # != live
    assert any("post-anchor" in e for e in verify_against_anchors(rows, anchors))


# ---------------- reconcile outbox gaps ----------------


def test_find_terminal_gaps_flags_missing_terminal_event():
    cps = [{"run_id": "r1", "tenant_id": "t1", "status": "completed"}]
    assert find_terminal_gaps(cps, []) == [
        {"run_id": "r1", "tenant_id": "t1", "status": "completed", "missing_event": "run_completed"}
    ]


def test_find_terminal_gaps_none_when_present():
    cps = [{"run_id": "r1", "tenant_id": "t1", "status": "failed"}]
    rows = [{"run_id": "r1", "event_type": "run_failed"}]
    assert find_terminal_gaps(cps, rows) == []


def test_find_terminal_gaps_ignores_non_terminal():
    cps = [{"run_id": "r1", "tenant_id": "t1", "status": "paused"}]
    assert find_terminal_gaps(cps, []) == []
