-- Migration 0008 — Tier 3.1 audit log (append-only, hash-chained, per-tenant).
-- Design: docs/superpowers/specs/2026-07-23-durable-audit-log-design.md (D-AUDIT-1..8).
--
-- Apply on existing deployments AFTER 0007. Fresh installs get this folded into
-- schema.sql. Idempotent (IF NOT EXISTS / CREATE POLICY guarded by the caller).
--
-- ADVERSARY MODEL (D-AUDIT-2 §2): defends against a DB admin / superuser via
-- three layers — (1) hash chain, (2) append-only grants, (3) external WORM
-- anchor (see scripts/anchor_audit_chain.py). Only layer 3 reaches the
-- superuser; layers 1-2 stop the daemon role / app bug / unprivileged insider.
--
-- LOAD-BEARING PRECONDITION (like the 0007 FORCE-RLS): the daemon role MUST NOT
-- own this table. Append-only grants + FORCE RLS both rely on the daemon being a
-- non-owner. If daemon == owner, the append-only property is decorative.
--
-- HASH-BOUND FIELDS ARE app-owned TEXT (D-AUDIT-5 / review H2): `at`,
-- `extra_canonical`, and `hash_input` are TEXT the application serializes
-- byte-for-byte, NOT JSONB/TIMESTAMPTZ. This is deliberate — JSONB/TIMESTAMPTZ
-- normalize on store (key reorder, tz→UTC, µs precision) and would make the
-- walker's row_hash recompute mismatch an untouched row (false-positive tamper).
-- Do NOT "fix" `at` to TIMESTAMPTZ or `extra_canonical` to JSONB.

CREATE TABLE IF NOT EXISTS audit_log (
    tenant_id             VARCHAR(64)  NOT NULL,
    seq                   BIGINT       NOT NULL,   -- per-tenant chain position (PK, monotonic)
    run_id                VARCHAR(64)  NOT NULL,
    event_type            VARCHAR(48)  NOT NULL,
    event_seq             INTEGER      NOT NULL,   -- per-run event ordinal (D-AUDIT-6 idempotency)
    round                 INTEGER,
    at                    TEXT         NOT NULL,   -- app-canonical ISO-8601; hash-bound; NO default
    workflow_class        TEXT         NOT NULL,
    workflow_version_hash VARCHAR(16),
    executor_model        VARCHAR(128) NOT NULL,
    reviewer_model        VARCHAR(128) NOT NULL,
    content_hash          CHAR(64)     NOT NULL,
    extra_canonical       TEXT         NOT NULL DEFAULT '{}',  -- app-canonical JSON TEXT; hash-bound
    prev_hash             CHAR(64)     NOT NULL,   -- row_hash of the prior per-tenant row (genesis = 64 zeros)
    hash_input            TEXT         NOT NULL,   -- the exact canonical string that was hashed
    row_hash              CHAR(64)     NOT NULL,   -- sha256(hash_input)
    PRIMARY KEY (tenant_id, seq),
    CONSTRAINT audit_run_id_charset    CHECK (run_id    ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$'),
    CONSTRAINT audit_tenant_id_charset CHECK (tenant_id ~ '^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$'),
    CONSTRAINT audit_seq_positive      CHECK (seq >= 1),
    CONSTRAINT audit_event_seq_bounds  CHECK (event_seq >= 0),
    CONSTRAINT audit_content_hash_hex  CHECK (content_hash ~ '^[0-9a-f]{64}$'),
    CONSTRAINT audit_prev_hash_hex     CHECK (prev_hash    ~ '^[0-9a-f]{64}$'),
    CONSTRAINT audit_row_hash_hex      CHECK (row_hash     ~ '^[0-9a-f]{64}$'),
    CONSTRAINT audit_round_bounds      CHECK (round IS NULL OR (round >= 0 AND round <= 10000)),
    CONSTRAINT audit_event_type_enum   CHECK (event_type IN (
        'round_completed','round_converged','veto','force_accept',
        'model_upgrade','workflow_version_backfill','workflow_version_upgrade',
        'budget_cap_acknowledged','run_cancelled',
        'run_started','run_completed','run_failed')),  -- extend with 3.2 approval events
    CONSTRAINT audit_idempotent        UNIQUE (tenant_id, run_id, event_seq)
);

-- Head lookup (hot: every emit reads the per-tenant chain head).
CREATE INDEX IF NOT EXISTS idx_audit_tenant_seq ON audit_log (tenant_id, seq DESC);
-- Per-run trail (operator + reconcile + 3.2 attestation lookups).
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_log (tenant_id, run_id, seq);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
-- FORCE so the table owner is also subject to WITH CHECK (D-AUDIT-2 / 0007 HIGH-1).
ALTER TABLE audit_log FORCE  ROW LEVEL SECURITY;

-- SELECT unscoped (D-TENANT-3 convention: walker/reconcile poll across tenants).
CREATE POLICY audit_select_all ON audit_log
    FOR SELECT TO PUBLIC USING (true);
-- INSERT scoped to the GUC set via `SELECT set_config('app.tenant_id', $1, true)`.
CREATE POLICY audit_insert_scoped ON audit_log
    FOR INSERT TO PUBLIC
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
-- No UPDATE policy. No DELETE policy. Absence = denied under RLS (append-only at
-- the policy layer; the grant block below is the second, coarser layer).

-- Least-privilege grants (run after DDL; kept out of idempotent schema.sql):
--   GRANT SELECT, INSERT ON audit_log TO daemon_user;   -- NO UPDATE / DELETE / TRUNCATE
--   -- daemon_user MUST NOT own audit_log (append-only + FORCE RLS rely on non-owner).
--   GRANT SELECT ON audit_log TO auditor_ro;            -- walker / compliance read
