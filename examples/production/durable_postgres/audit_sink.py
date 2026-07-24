"""PostgresAuditSink — Tier 3.1 tamper-evident audit ledger (D-AUDIT-5).

Design: docs/superpowers/specs/2026-07-23-durable-audit-log-design.md.

Per-tenant hash chain, `pg_advisory_xact_lock` serialized, append-only
(SELECT+INSERT grants only, FORCE RLS, no UPDATE/DELETE policy). App-side hash
compute over an app-owned canonical TEXT `hash_input` (review finding H2): the
hash never binds JSONB/TIMESTAMPTZ columns that normalize on store, so the
walker's recompute cannot false-positive on an untouched row.

INVERTED-RAISE CONTRACT (D-AUDIT-1, differs from the metrics sink): `emit` MUST
propagate on failure so the durable layer's outbox reconcile retries. A
swallow-and-log here silently drops an audit row and defeats tamper-evidence.

SQL INJECTION POSTURE: every dynamic value uses asyncpg $N parameters; no
f-strings in SQL (enforced by scripts/check_no_fstring_sql.sh). tenant_id is
charset-validated at the app layer before any DB call, mirroring store.py.
"""
from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any, Mapping

if TYPE_CHECKING:  # avoid importing asyncpg at module load so the pure
    import asyncpg  # canonical/hash helpers are usable without the DB driver

    from adv_multi_agent.core.durable.audit import AuditEvent

# Genesis link for the first row of a per-tenant chain.
GENESIS_PREV_HASH = "0" * 64


def canonical_extra(extra: Mapping[str, Any]) -> str:
    """Deterministic JSON TEXT for the `extra_canonical` column (hash-bound)."""
    return json.dumps(dict(extra), sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def audit_hash_input(
    *,
    tenant_id: str,
    seq: int,
    run_id: str,
    event_type: str,
    event_seq: int,
    round_: int | None,
    at: str,
    workflow_class: str,
    workflow_version_hash: str | None,
    executor_model: str,
    reviewer_model: str,
    content_hash: str,
    extra_canonical: str,
    prev_hash: str,
) -> str:
    """The exact canonical string that gets hashed into `row_hash`.

    Stored verbatim in the `hash_input` TEXT column so the walker re-hashes
    identical bytes (H2). `prev_hash` is included so each row commits to its
    predecessor (the chain link). Sorted keys + compact separators + NFC-free
    (callers pass already-normalized model strings) keeps it reproducible across
    library versions and between the writer and the walker.
    """
    payload = {
        "at": at,
        "content_hash": content_hash,
        "event_seq": event_seq,
        "event_type": event_type,
        "executor_model": executor_model,
        "extra_canonical": extra_canonical,
        "prev_hash": prev_hash,
        "resolved_round": round_,
        "reviewer_model": reviewer_model,
        "run_id": run_id,
        "seq": seq,
        "tenant_id": tenant_id,
        "workflow_class": workflow_class,
        "workflow_version_hash": workflow_version_hash,
    }
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def row_hash_of(hash_input: str) -> str:
    return hashlib.sha256(hash_input.encode("utf-8")).hexdigest()


class PostgresAuditSink:
    """AuditSink over asyncpg. See module docstring + 0008_add_audit_log.sql."""

    def __init__(self, pool: "asyncpg.Pool") -> None:
        self._pool = pool

    async def emit(self, event: "AuditEvent") -> None:
        # Lazy import: keeps the module (and its pure helpers) importable
        # without asyncpg installed, for unit-testing the chain logic.
        from .store import _validate_tenant_id

        tenant = _validate_tenant_id(event.tenant_id)
        extra_canonical = canonical_extra(event.extra)
        lock_key = f"audit:{tenant}"
        async with self._pool.acquire() as conn:
            async with conn.transaction():
                # RLS INSERT policy requires the GUC (SET LOCAL via set_config).
                await conn.execute(
                    "SELECT set_config('app.tenant_id', $1, true)", tenant
                )
                # Per-tenant serialization for the read-head -> INSERT window.
                # Held for the whole txn; different tenants never contend.
                await conn.execute(
                    "SELECT pg_advisory_xact_lock(hashtext($1))", lock_key
                )
                head = await conn.fetchrow(
                    "SELECT seq, row_hash FROM audit_log "
                    "WHERE tenant_id = $1 ORDER BY seq DESC LIMIT 1",
                    tenant,
                )
                if head is None:
                    seq = 1
                    prev_hash = GENESIS_PREV_HASH
                else:
                    seq = int(head["seq"]) + 1
                    prev_hash = str(head["row_hash"])
                hash_input = audit_hash_input(
                    tenant_id=tenant,
                    seq=seq,
                    run_id=event.run_id,
                    event_type=event.event_type,
                    event_seq=event.event_seq,
                    round_=event.round,
                    at=event.at,
                    workflow_class=event.workflow_class,
                    workflow_version_hash=event.workflow_version_hash,
                    executor_model=event.executor_model,
                    reviewer_model=event.reviewer_model,
                    content_hash=event.content_hash,
                    extra_canonical=extra_canonical,
                    prev_hash=prev_hash,
                )
                row_hash = row_hash_of(hash_input)
                # ON CONFLICT DO NOTHING (bare) covers both the (tenant_id, seq)
                # PK and the UNIQUE(tenant_id, run_id, event_seq) idempotency key,
                # so a crash-retry re-emit is a no-op and never forks the chain.
                await conn.execute(
                    """
                    INSERT INTO audit_log
                      (tenant_id, seq, run_id, event_type, event_seq, round, at,
                       workflow_class, workflow_version_hash, executor_model,
                       reviewer_model, content_hash, extra_canonical, prev_hash,
                       hash_input, row_hash)
                    VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)
                    ON CONFLICT DO NOTHING
                    """,
                    tenant,
                    seq,
                    event.run_id,
                    event.event_type,
                    event.event_seq,
                    event.round,
                    event.at,
                    event.workflow_class,
                    event.workflow_version_hash,
                    event.executor_model,
                    event.reviewer_model,
                    event.content_hash,
                    extra_canonical,
                    prev_hash,
                    hash_input,
                    row_hash,
                )
