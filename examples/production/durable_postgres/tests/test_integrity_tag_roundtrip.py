"""Tier 1.9 closure tests — integrity_tag + workflow_version_hash round-trip.

The 2026-05-18 rotation drill (Tier 1.5-EVE) found that PostgresCheckpointStore
silently dropped both optional Checkpoint fields on write and never repopulated
them on read. This file pins the fix:

  - integrity_tag: stored in body JSON + denormalized column mirror
  - workflow_version_hash: stored in body JSON only
  - _row_to_token includes workflow_version_hash for daemon resume path
  - legacy rows (pre-fix payload without these keys) still read clean with
    None defaults — backward compatible

Gated by needs_postgres (auto-skip without POSTGRES_DSN).
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pytest

from adv_multi_agent.core.durable.checkpoint import Checkpoint

from examples.production.durable_postgres.store import PostgresCheckpointStore
from examples.production.durable_postgres.tests.conftest import needs_postgres


pytestmark = [pytest.mark.asyncio, needs_postgres]


_WF_CLASS = "x.Y.RoundtripWorkflow"


def _cp(
    run_id: str,
    *,
    integrity_tag: str | None = None,
    workflow_version_hash: str | None = None,
) -> Checkpoint:
    now = datetime.now(timezone.utc).isoformat()
    return Checkpoint(
        run_id=run_id,
        tenant_id="_default",
        schema_version=1,
        status="paused",
        round=1,
        rounds_history=[{"round": 1}],
        last_request_json='{"roundtrip": true}',
        pause_reason="rolling_data",
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="claude-opus-4-7",
        pinned_reviewer_model="gpt-4o",
        wake_at=None,
        created_at=now,
        updated_at=now,
        workflow_version_hash=workflow_version_hash,
        integrity_tag=integrity_tag,
    )


def _store(pg_pool: Any) -> PostgresCheckpointStore:
    return PostgresCheckpointStore(pg_pool, default_workflow_class=_WF_CLASS)


# ---------------------------------------------------------------------------
# Round-trip: write + read preserves both optional fields
# ---------------------------------------------------------------------------


async def test_integrity_tag_roundtrips(pg_pool, fresh_checkpoints_table):
    store = _store(pg_pool)
    tag = "SEAL:v1:abc123-fixture-tag"
    await store.write(_cp("rt-tag-1", integrity_tag=tag))
    loaded = await store.read("rt-tag-1")
    assert loaded.integrity_tag == tag


async def test_workflow_version_hash_roundtrips(pg_pool, fresh_checkpoints_table):
    store = _store(pg_pool)
    h = "deadbeefcafebabe"  # 16-char lowercase hex per token._HASH_RE
    await store.write(_cp("rt-wvh-1", workflow_version_hash=h))
    loaded = await store.read("rt-wvh-1")
    assert loaded.workflow_version_hash == h


async def test_both_fields_roundtrip_together(pg_pool, fresh_checkpoints_table):
    store = _store(pg_pool)
    tag = "SEAL:v1:multi-tag"
    h = "0123456789abcdef"
    await store.write(_cp("rt-both", integrity_tag=tag, workflow_version_hash=h))
    loaded = await store.read("rt-both")
    assert loaded.integrity_tag == tag
    assert loaded.workflow_version_hash == h


async def test_none_fields_roundtrip_as_none(pg_pool, fresh_checkpoints_table):
    """Defaults: both fields None should round-trip to None (not "None" string)."""
    store = _store(pg_pool)
    await store.write(_cp("rt-none"))
    loaded = await store.read("rt-none")
    assert loaded.integrity_tag is None
    assert loaded.workflow_version_hash is None


# ---------------------------------------------------------------------------
# Denormalized column mirror (integrity_tag) — for reseal partial index
# ---------------------------------------------------------------------------


async def test_integrity_tag_column_mirrors_body(
    pg_pool, fresh_checkpoints_table,
):
    """The schema's integrity_tag column is denormalized for the reseal
    partial index `checkpoints_integrity_tag_null_idx`. The body JSON is the
    canonical source; the column must mirror it on every write.
    """
    store = _store(pg_pool)
    tag = "SEAL:v1:column-mirror-check"
    await store.write(_cp("rt-col-1", integrity_tag=tag))
    async with pg_pool.acquire() as conn:
        col_value = await conn.fetchval(
            "SELECT integrity_tag FROM checkpoints WHERE run_id = $1",
            "rt-col-1",
        )
        payload = await conn.fetchval(
            "SELECT payload FROM checkpoints WHERE run_id = $1", "rt-col-1",
        )
    assert col_value == tag
    body = json.loads(bytes(payload).decode("utf-8"))
    assert body["integrity_tag"] == tag


async def test_integrity_tag_column_null_when_none(
    pg_pool, fresh_checkpoints_table,
):
    store = _store(pg_pool)
    await store.write(_cp("rt-col-none"))
    async with pg_pool.acquire() as conn:
        col_value = await conn.fetchval(
            "SELECT integrity_tag FROM checkpoints WHERE run_id = $1",
            "rt-col-none",
        )
    assert col_value is None


# ---------------------------------------------------------------------------
# Update path — write_if_unchanged preserves both fields
# ---------------------------------------------------------------------------


async def test_write_if_unchanged_preserves_integrity_tag(
    pg_pool, fresh_checkpoints_table,
):
    """The rotation sweep path: read → re-seal → write_if_unchanged. The new
    tag must land in both body and column on the CAS update.
    """
    store = _store(pg_pool)
    initial_tag = "SEAL:v1:initial"
    await store.write(_cp("rt-cas", integrity_tag=initial_tag))

    async with pg_pool.acquire() as conn:
        existing_updated_at = await conn.fetchval(
            "SELECT updated_at FROM checkpoints WHERE run_id = $1", "rt-cas",
        )

    new_tag = "SEAL:v1:after-rotation"
    cp2 = _cp("rt-cas", integrity_tag=new_tag)
    await store.write_if_unchanged(
        cp2, expected_updated_at=existing_updated_at, workflow_class=_WF_CLASS,
    )

    loaded = await store.read("rt-cas")
    assert loaded.integrity_tag == new_tag
    async with pg_pool.acquire() as conn:
        col_value = await conn.fetchval(
            "SELECT integrity_tag FROM checkpoints WHERE run_id = $1", "rt-cas",
        )
    assert col_value == new_tag


# ---------------------------------------------------------------------------
# Backward compatibility — legacy payloads (pre-fix) still read clean
# ---------------------------------------------------------------------------


async def test_legacy_payload_without_keys_reads_with_none(
    pg_pool, fresh_checkpoints_table,
):
    """Rows written by the pre-fix code carry a payload body WITHOUT
    integrity_tag / workflow_version_hash keys. _deserialize must tolerate
    that — body.get() returns None — so the unseal warning path remains the
    upgrade signal (not a hard crash).
    """
    legacy_body = {
        "round": 1,
        "rounds_history": [{"round": 1}],
        "last_request_json": '{"legacy": true}',
        "pause_reason": "rolling_data",
        "pause_context": {},
        "budget_used": {"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        "pinned_executor_model": "claude-opus-4-7",
        "pinned_reviewer_model": "gpt-4o",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
        # NOTE: deliberately no integrity_tag, no workflow_version_hash
    }
    payload_bytes = json.dumps(legacy_body).encode("utf-8")
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO checkpoints "
            "(run_id, schema_version, status, workflow_class, payload) "
            "VALUES ($1, 1, 'paused', $2, $3)",
            "rt-legacy", _WF_CLASS, payload_bytes,
        )
    loaded = await _store(pg_pool).read("rt-legacy")
    assert loaded.integrity_tag is None
    assert loaded.workflow_version_hash is None
    assert loaded.run_id == "rt-legacy"


# ---------------------------------------------------------------------------
# list_paused → ResumeToken includes workflow_version_hash
# ---------------------------------------------------------------------------


async def test_list_paused_token_includes_workflow_version_hash(
    pg_pool, fresh_checkpoints_table,
):
    store = _store(pg_pool)
    h = "feedfacecafebabe"
    await store.write(_cp("rt-tok-1", workflow_version_hash=h))
    tokens = await store.list_paused(wake_before=datetime.now(timezone.utc))
    assert len(tokens) == 1
    assert tokens[0].workflow_version_hash == h


async def test_list_paused_token_legacy_payload_yields_none(
    pg_pool, fresh_checkpoints_table,
):
    legacy_body = {
        "round": 1,
        "rounds_history": [{"round": 1}],
        "last_request_json": '{"legacy": true}',
        "pause_reason": "rolling_data",
        "pause_context": {},
        "budget_used": {},
        "pinned_executor_model": "claude-opus-4-7",
        "pinned_reviewer_model": "gpt-4o",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    payload_bytes = json.dumps(legacy_body).encode("utf-8")
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "INSERT INTO checkpoints "
            "(run_id, schema_version, status, workflow_class, payload) "
            "VALUES ($1, 1, 'paused', $2, $3)",
            "rt-tok-legacy", _WF_CLASS, payload_bytes,
        )
    tokens = await _store(pg_pool).list_paused(
        wake_before=datetime.now(timezone.utc),
    )
    assert len(tokens) == 1
    assert tokens[0].workflow_version_hash is None
