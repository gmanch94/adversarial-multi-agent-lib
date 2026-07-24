"""Tier 3.1 audit-log — LIVE Postgres integration (needs_postgres).

Complements the pure-logic `test_audit_sink.py` (chain math on fabricated dicts)
by exercising the DB layer that pure tests cannot reach:
  1. **SQL parse-check** — `fresh_checkpoints_table` applies `schema.sql` (which
     now folds in the `audit_log` DDL + indexes + RLS policies), so a typo in
     `0008`/the folded block fails collection here.
  2. **Chain append** — `PostgresAuditSink.emit` assigns seq, links prev_hash,
     and `row_hash = sha256(hash_input)` against a real advisory-lock + INSERT
     (also exercises `pg_advisory_xact_lock(hashtext($1)::bigint)`).
  3. **Idempotency** — a repeat (run_id, event_seq) is a no-op via ON CONFLICT.
  4. **RLS WITH CHECK** — a cross-tenant INSERT (GUC != row tenant) is rejected.

Skipped unless POSTGRES_DSN is set (same gate as test_tenant_isolation.py). Bring
up the sibling DB via `docker compose up postgres` and set POSTGRES_DSN. NOTE:
append-only GRANT enforcement (SELECT+INSERT only, no UPDATE/DELETE) needs a
non-owner role the test harness does not provision — that cell is verified at
deploy time per the runbook §3.1 checklist, not here.
"""
from __future__ import annotations

import hashlib

import pytest

from adv_multi_agent.core.durable.audit import AuditEvent
from examples.production.durable_postgres.audit_sink import (
    GENESIS_PREV_HASH,
    PostgresAuditSink,
)

from .conftest import needs_postgres

pytestmark = [pytest.mark.asyncio, needs_postgres]

_TENANT = "t-audit"


def _event(event_seq: int, *, run_id: str = "run-audit-1", event_type: str = "round_completed",
           tenant_id: str = _TENANT, content_hash: str | None = None) -> AuditEvent:
    return AuditEvent(
        run_id=run_id, tenant_id=tenant_id, event_type=event_type, event_seq=event_seq,
        round=1, at="2026-07-23T00:00:00+00:00", workflow_class="pkg.Wf",
        executor_model="claude-opus-4-7", reviewer_model="gpt-4o",
        content_hash=content_hash or ("a" * 64),
    )


async def test_emit_builds_linked_chain(pg_pool, fresh_checkpoints_table):
    sink = PostgresAuditSink(pg_pool)
    await sink.emit(_event(0, event_type="run_started"))
    await sink.emit(_event(1))
    async with pg_pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT seq, prev_hash, row_hash, hash_input FROM audit_log "
            "WHERE tenant_id = $1 ORDER BY seq ASC",
            _TENANT,
        )
    assert [r["seq"] for r in rows] == [1, 2]
    assert rows[0]["prev_hash"] == GENESIS_PREV_HASH
    assert rows[1]["prev_hash"] == rows[0]["row_hash"]
    for r in rows:
        assert hashlib.sha256(r["hash_input"].encode("utf-8")).hexdigest() == r["row_hash"]


async def test_emit_dedup_on_event_seq(pg_pool, fresh_checkpoints_table):
    sink = PostgresAuditSink(pg_pool)
    await sink.emit(_event(0, event_type="run_started"))
    await sink.emit(_event(0, event_type="run_started"))  # same (run, event_seq)
    async with pg_pool.acquire() as conn:
        n = await conn.fetchval(
            "SELECT count(*) FROM audit_log WHERE tenant_id = $1 AND run_id = $2 AND event_seq = 0",
            _TENANT, "run-audit-1",
        )
    assert n == 1


async def test_rls_blocks_cross_tenant_insert(pg_pool, fresh_checkpoints_table):
    """GUC set to tenant A, row tenant B → RLS WITH CHECK rejects."""
    with pytest.raises(Exception):  # asyncpg raises on the failed WITH CHECK
        async with pg_pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("SELECT set_config('app.tenant_id', $1, true)", "t-a")
                await conn.execute(
                    """
                    INSERT INTO audit_log
                      (tenant_id, seq, run_id, event_type, event_seq, round, at,
                       workflow_class, executor_model, reviewer_model, content_hash,
                       prev_hash, hash_input, row_hash)
                    VALUES ('t-b', 1, 'run-x', 'run_started', 0, 0, 'x', 'c',
                            'e', 'rv', $1, $2, 'hi', $3)
                    """,
                    "a" * 64, GENESIS_PREV_HASH, "b" * 64,
                )
