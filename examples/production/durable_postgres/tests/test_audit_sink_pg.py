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
up a Postgres and set POSTGRES_DSN. The append-only-grant + RLS test provisions
its OWN NOSUPERUSER role (a superuser bypasses RLS by design, so the plain
image's superuser `daemon` cannot exercise layer 2) — so this suite verifies the
real non-superuser threat, not just the happy path.

Verified live 2026-07-24 (throwaway postgres:16-alpine): 3/3 pass — chain append
+ prev_hash link + row_hash=sha256(hash_input) + advisory-lock + hashtext::bigint
(layer 1); ON CONFLICT dedup; RLS-reject-cross-tenant + append-only-grant-reject
UPDATE/DELETE against a real NOSUPERUSER role (layer 2).
"""
from __future__ import annotations

import hashlib
import os
from urllib.parse import urlparse

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


_INSERT_SQL = """
    INSERT INTO audit_log
      (tenant_id, seq, run_id, event_type, event_seq, round, at,
       workflow_class, executor_model, reviewer_model, content_hash,
       prev_hash, hash_input, row_hash)
    VALUES ($1, $2, 'run-x', 'run_started', $3, 0, 'x', 'c',
            'e', 'rv', $4, $5, 'hi', $6)
"""


async def test_rls_and_append_only_grants_for_nonsuperuser(pg_pool, fresh_checkpoints_table):
    """RLS + append-only grants only bind a NON-superuser (superusers bypass RLS
    by design — that's why the plain image's `daemon` superuser can't test this).
    Create a NOSUPERUSER role with only SELECT+INSERT and prove the real layer-2
    defense: legit INSERT works, cross-tenant INSERT is RLS-rejected, and
    UPDATE/DELETE are grant-denied (append-only)."""
    import asyncpg

    role, pw = "audit_nonsuper", "testpass2"
    async with pg_pool.acquire() as conn:
        await conn.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='audit_nonsuper') "
            "THEN CREATE ROLE audit_nonsuper LOGIN PASSWORD 'testpass2' NOSUPERUSER; END IF; END $$;"
        )
        # Append-only grant: SELECT + INSERT only, never UPDATE/DELETE.
        await conn.execute("GRANT SELECT, INSERT ON audit_log TO audit_nonsuper")
    # Seed one row (via the superuser sink) so UPDATE/DELETE have a target.
    await PostgresAuditSink(pg_pool).emit(_event(0, event_type="run_started"))

    u = urlparse(os.environ["POSTGRES_DSN"])
    conn2 = await asyncpg.connect(
        user=role, password=pw, host=u.hostname, port=u.port, database=u.path.lstrip("/")
    )
    try:
        # (a) UPDATE denied by grant (append-only).
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn2.execute("UPDATE audit_log SET row_hash = $1", "f" * 64)
        # (b) DELETE denied by grant (append-only).
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            await conn2.execute("DELETE FROM audit_log")
        # (c) cross-tenant INSERT rejected by RLS WITH CHECK (GUC t-a, row t-b).
        with pytest.raises(asyncpg.InsufficientPrivilegeError):
            async with conn2.transaction():
                await conn2.execute("SELECT set_config('app.tenant_id', $1, true)", "t-a")
                await conn2.execute(_INSERT_SQL, "t-b", 90, 5, "a" * 64, GENESIS_PREV_HASH, "b" * 64)
        # (d) legit INSERT (GUC matches row tenant) succeeds under the same role.
        async with conn2.transaction():
            await conn2.execute("SELECT set_config('app.tenant_id', $1, true)", "t-b")
            await conn2.execute(_INSERT_SQL, "t-b", 91, 6, "a" * 64, GENESIS_PREV_HASH, "b" * 64)
        n = await conn2.fetchval("SELECT count(*) FROM audit_log WHERE tenant_id = 't-b'")
        assert n == 1
    finally:
        await conn2.close()
