"""AuditSink Protocol + NoopAuditSink + AuditEvent (Tier 3.1 audit log).

Design: docs/superpowers/specs/2026-07-23-durable-audit-log-design.md (D-AUDIT-1..8).

The library defines a small structured-audit seam so operators can wire a
tamper-evident ledger (the sibling `PostgresAuditSink` under
`examples/production/durable_postgres/`) without the library depending on
Postgres. The default `NoopAuditSink` is a zero-overhead no-op.

INVERTED-RAISE CONTRACT (D-AUDIT-1, differs from MetricsBackend):
`MetricsBackend.emit`-style calls MUST NOT raise (telemetry never breaks the
workflow). `AuditSink.emit` is the OPPOSITE: a real sink MUST propagate on
failure so the durable layer sees the miss and lets the outbox reconcile
(D-AUDIT-7) retry it. A swallow-and-log inside the sink silently drops an audit
row and defeats the tamper-evidence guarantee. Only `NoopAuditSink.emit` never
raises. The durable layer — not the sink — is what catches the exception and
continues the run (the row becomes an outbox gap, closed on resume/sweep).

PHI boundary (D-AUDIT-2 / Tier 1.7): an `AuditEvent` carries a `content_hash`
of the model I/O, never the raw text. `extra` keys are drawn from a closed
non-PHI allowlist and values are scalars only — no free-text ever lands in a
row. There is deliberately no `error` field: exception messages routinely echo
input and would leak PHI into an append-only WORM-anchored table that cannot be
shredded (3.3).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Mapping, Protocol, runtime_checkable

# D-AUDIT-4: closed event_type enum. Mirrors the DB CHECK in
# examples/production/durable_postgres/scripts/0008_add_audit_log.sql.
# 3.2 approval events (approval_requested/granted/rejected) join this set then.
AUDIT_EVENT_TYPES: frozenset[str] = frozenset({
    "round_completed",
    "round_converged",
    "veto",
    "force_accept",
    "model_upgrade",
    "workflow_version_backfill",
    "workflow_version_upgrade",
    "budget_cap_acknowledged",
    "run_cancelled",
    "run_started",
    "run_completed",
    "run_failed",
})

# D-AUDIT-2 / M1: closed non-PHI allowlist for `extra` keys. Values are scalars
# only. Nothing free-text, so nothing PHI-shaped can land in the append-only row.
AUDIT_EXTRA_KEYS: frozenset[str] = frozenset({
    "score",
    "converged",
    "vetoed",
    "field",
    "from_model",
    "to_model",
    "pause_reason",
    "flag_count",
    "cap_usd",
    "note",
})

_HEX64_RE = re.compile(r"^[0-9a-f]{64}$")
_MAX_EXTRA_VALUE_CHARS = 200

# sha256(b"") — content_hash for lifecycle / contentless events (D-AUDIT-2).
EMPTY_CONTENT_HASH = hashlib.sha256(b"").hexdigest()
# Sentinel for pre-feature (legacy) round entries that carry no content_hash:
# an explicit "attestation gap" marker, same posture as the pre-1.6
# workflow_version back-fill. Distinct from EMPTY_CONTENT_HASH so an auditor can
# tell "empty input" from "input existed but was never hashed".
LEGACY_CONTENT_HASH = "0" * 64


@dataclass(frozen=True)
class AuditEvent:
    """One immutable decision record. Binds content by hash, never stores it.

    `event_seq` is the per-run event ordinal (D-AUDIT-6): 0 for run_started,
    i+1 for rounds_history[i], len+1 for the terminal event. It is derived
    deterministically from the persisted checkpoint, so a crash-retry re-derives
    the identical ordinal and the sink's UNIQUE(tenant_id, run_id, event_seq)
    dedupes. It also distinguishes two same-type events in one run (e.g. an
    executor + a reviewer model_upgrade) that a (round, event_type) key collides.
    """

    run_id: str
    tenant_id: str
    event_type: str
    event_seq: int
    round: int
    at: str
    workflow_class: str
    executor_model: str
    reviewer_model: str
    content_hash: str
    workflow_version_hash: str | None = None
    extra: Mapping[str, str | int | float | bool] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.event_type not in AUDIT_EVENT_TYPES:
            raise ValueError(
                f"event_type {self.event_type!r} not in {sorted(AUDIT_EVENT_TYPES)}"
            )
        for name in ("run_id", "tenant_id", "at", "workflow_class",
                     "executor_model", "reviewer_model"):
            v = getattr(self, name)
            if not isinstance(v, str) or not v:
                raise ValueError(f"{name} must be a non-empty str, got {v!r}")
        # Mirror the DB VARCHAR(128) caps so an over-long model string surfaces
        # as a loud construction error, not a silent fail-open INSERT drop.
        for name in ("executor_model", "reviewer_model"):
            if len(getattr(self, name)) > 128:
                raise ValueError(f"{name} exceeds 128 chars (DB VARCHAR(128) cap)")
        if not _HEX64_RE.fullmatch(self.content_hash):
            raise ValueError(
                f"content_hash must be 64 lowercase hex chars, got {self.content_hash!r}"
            )
        if self.workflow_version_hash is not None and not re.fullmatch(
            r"[0-9a-f]{16}", self.workflow_version_hash
        ):
            raise ValueError(
                f"workflow_version_hash must be 16 lowercase hex or None, "
                f"got {self.workflow_version_hash!r}"
            )
        # bool is a subclass of int — reject it for the integer fields explicitly.
        if not isinstance(self.event_seq, int) or isinstance(self.event_seq, bool) or self.event_seq < 0:
            raise ValueError(f"event_seq must be a non-negative int, got {self.event_seq!r}")
        if (not isinstance(self.round, int) or isinstance(self.round, bool)
                or self.round < 0 or self.round > 10000):
            raise ValueError(
                f"round must be an int in [0, 10000] (DB CHECK), got {self.round!r}"
            )
        if not isinstance(self.extra, Mapping):
            raise ValueError(f"extra must be a mapping, got {type(self.extra).__name__}")
        for k, v in self.extra.items():
            if k not in AUDIT_EXTRA_KEYS:
                raise ValueError(
                    f"extra key {k!r} not in allowlist {sorted(AUDIT_EXTRA_KEYS)} "
                    f"(D-AUDIT-2: closed non-PHI key set)"
                )
            # Order matters: bool before int (bool is a subclass of int).
            if isinstance(v, bool):
                continue
            if isinstance(v, (int, float)):
                continue
            if isinstance(v, str):
                if len(v) > _MAX_EXTRA_VALUE_CHARS:
                    raise ValueError(
                        f"extra[{k!r}] str length {len(v)} > cap {_MAX_EXTRA_VALUE_CHARS}"
                    )
                continue
            raise ValueError(
                f"extra[{k!r}] must be a scalar (str/int/float/bool), "
                f"got {type(v).__name__}"
            )


@runtime_checkable
class AuditSink(Protocol):
    """Tamper-evident ledger seam. See module docstring for the inverted-raise
    contract: a real implementation MUST propagate on failure."""

    async def emit(self, event: AuditEvent) -> None:
        """Append one event to the ledger. MUST be idempotent on
        (tenant_id, run_id, event_seq) so an outbox re-derivation is a no-op.
        MUST propagate on failure (do NOT swallow) — the durable layer catches
        it and reconciles later."""
        ...


class NoopAuditSink:
    """Default zero-overhead sink. Swallows every call (the only sink allowed
    to). Implements AuditSink by structural typing."""

    async def emit(self, event: AuditEvent) -> None:
        return


__all__ = [
    "AuditEvent",
    "AuditSink",
    "NoopAuditSink",
    "AUDIT_EVENT_TYPES",
    "AUDIT_EXTRA_KEYS",
    "EMPTY_CONTENT_HASH",
    "LEGACY_CONTENT_HASH",
]
