-- Reference checkpoints schema for examples/production/durable_postgres/.
-- See docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md §4.2
--
-- Migration sequence (apply in order on existing deployments):
--   0001 = initial schema (this file as of 2026-05-16; no separate file)
--   0002 = scripts/0002_add_integrity_tag.sql       (Tier 1.9 / A10-H2 closure)
--   0003 = scripts/0003_add_quarantine.sql          (Tier 2.4 / quarantine + dead-letter)
--   0004 = scripts/0004_add_tenant_id.sql           (Tier 2.1a / tenant_id nullable + CHECK)
--   0005 = scripts/0005_enable_tenant_rls.sql       (Tier 2.1a / RLS policies; apply AFTER backfill)
--   0006 = scripts/0006_tenant_id_not_null.sql      (Tier 2.1a / NOT NULL flip; apply AFTER backfill)
--   0007 = scripts/0007_force_tenant_rls.sql        (Tier 2.1d / FORCE RLS)
--   0008 = scripts/0008_add_audit_log.sql           (Tier 3.1 / append-only hash-chained audit log)
--
-- Fresh installs run this file once; it includes every column from every
-- migration so a clean DB never needs the 000N_*.sql files.
--
-- D-TENANT-0 (Tier 2.1a): this schema includes tenant_id NOT NULL +
-- RLS policies for multi-tenant isolation. Operators using single-tenant
-- deployments pass tenant_id='_default' on every write — see runbook §5.6.

CREATE TABLE IF NOT EXISTS checkpoints (
    run_id           VARCHAR(64) PRIMARY KEY,
    tenant_id        VARCHAR(64) NOT NULL,
    schema_version   INTEGER NOT NULL,
    status           VARCHAR(32) NOT NULL,
    wake_at          TIMESTAMPTZ,
    workflow_class   TEXT NOT NULL,
    payload          BYTEA NOT NULL,
    integrity_tag    TEXT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT run_id_charset CHECK (run_id ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$'),
    CONSTRAINT tenant_id_charset CHECK (tenant_id ~ '^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$'),
    CONSTRAINT workflow_class_length CHECK (char_length(workflow_class) <= 512)
    -- F-M-07: payload is BYTEA NOT NULL. Smallest valid JSON object is "{}"
    -- (2 bytes). If a future migration adds CHECK (length(payload) > N),
    -- N must be <= 2 OR the migration must rewrite legacy rows.
    --
    -- A10-H2 (Tier 1.9): integrity_tag is a denormalized mirror of the value
    -- inside the serialized payload. The library does NOT read this column;
    -- it exists only so the reseal_all_checkpoints.py script can scan for
    -- legacy rows (integrity_tag IS NULL) via the partial index below.
    --
    -- D-TENANT-1 (Tier 2.1a): tenant_id is a first-class column for RLS
    -- policy enforcement (see policies block below). Charset mirrors run_id
    -- but allows leading `_` for reserved `_default` / `_legacy` tenants.
);

-- Partial index supports the hot list_paused query.
CREATE INDEX IF NOT EXISTS idx_paused_wake
    ON checkpoints (wake_at NULLS LAST)
    WHERE status = 'paused';

-- D-TENANT-1 (Tier 2.1a): composite index for tenant-scoped poll.
-- Post-2.1a the scheduler will optionally call list_paused_by_tenant(tenant_id)
-- and Tier 3.4 (tenant-shard scheduling) makes this the primary poll index.
CREATE INDEX IF NOT EXISTS idx_paused_tenant_wake
    ON checkpoints (tenant_id, wake_at NULLS LAST)
    WHERE status = 'paused';

-- Partial index supports the reseal script's pending-row scan (Tier 1.9).
CREATE INDEX IF NOT EXISTS checkpoints_integrity_tag_null_idx
    ON checkpoints (run_id)
    WHERE integrity_tag IS NULL;

-- Tier 2.4 quarantine table. Populated by the sibling QuarantineSync task
-- (examples/production/durable_postgres/quarantine.py). The library does NOT
-- write this table — the sibling snapshots the daemon's in-memory _quarantine
-- set each poll and INSERTs new entries. Operator scripts read this table
-- (scripts/list_quarantined.py) and signal requeue by setting requeued_at
-- (scripts/requeue.py); the sibling's poll then discards from in-memory.
--
-- run_id mirrors checkpoints.run_id but no FK — a run can be quarantined
-- before its checkpoint is written, and we keep history after row deletion.
CREATE TABLE IF NOT EXISTS quarantine (
    run_id           VARCHAR(64) PRIMARY KEY,
    tenant_id        VARCHAR(64) NOT NULL,
    quarantined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    failure_count    INTEGER NOT NULL,
    reason           VARCHAR(32) NOT NULL,
    requeued_at      TIMESTAMPTZ,
    requeue_count    INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT quarantine_run_id_charset CHECK (run_id ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$'),
    CONSTRAINT quarantine_tenant_id_charset CHECK (tenant_id ~ '^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$'),
    CONSTRAINT quarantine_reason_enum CHECK (
        reason IN ('max_retries_exceeded', 'manual', 'unknown')
    ),
    CONSTRAINT quarantine_failure_count_bounds CHECK (
        failure_count >= 0 AND failure_count <= 1000
    )
);

-- A14-M-01: partial index covers the operator-facing list_quarantined hot
-- path (filters active runs WHERE requeued_at IS NULL). The requeue-poll
-- path scans WHERE requeued_at IS NOT NULL but is low-frequency + bounded
-- by the rate at which operators set requeued_at — sequential scan acceptable
-- for that side.
CREATE INDEX IF NOT EXISTS idx_quarantine_active
    ON quarantine (quarantined_at DESC)
    WHERE requeued_at IS NULL;

-- D-TENANT-1 (Tier 2.1a): tenant-scoped quarantine list hot path.
CREATE INDEX IF NOT EXISTS idx_quarantine_tenant_active
    ON quarantine (tenant_id, quarantined_at DESC)
    WHERE requeued_at IS NULL;

-- =========================================================================
-- D-TENANT-3 (Tier 2.1a): Row-Level Security policies.
-- =========================================================================
-- SELECT is unscoped (USING true) so the scheduler can poll across tenants.
-- INSERT/UPDATE/DELETE require current_setting('app.tenant_id') to match
-- the row's tenant_id. The GUC MUST be set via `SET LOCAL app.tenant_id = $1`
-- inside an explicit transaction (async with conn.transaction()) — `SET`
-- without LOCAL would leak the GUC to the next connection-pool checkout.
-- store.py CI grep gate (scripts/check_set_local_pattern.py) enforces.

ALTER TABLE checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE quarantine  ENABLE ROW LEVEL SECURITY;

-- D-TENANT-FORCE-RLS (Tier 2.1d audit HIGH-1): FORCE RLS so the table owner
-- is also subject to WITH CHECK. Without FORCE, the role that owns the
-- table (typically the role running this schema.sql) bypasses every RLS
-- policy — cross-tenant writes succeed silently. PRECONDITION: deploy with
-- a non-owner daemon role. If daemon = owner, FORCE is decorative but no
-- worse than non-FORCE. Fresh deploys get this baked in; existing 2.1a/b/c
-- deploys apply via migration script 0007_force_tenant_rls.sql.
ALTER TABLE checkpoints FORCE ROW LEVEL SECURITY;
ALTER TABLE quarantine  FORCE ROW LEVEL SECURITY;

CREATE POLICY tenant_select_all_checkpoints ON checkpoints
    FOR SELECT TO PUBLIC USING (true);
CREATE POLICY tenant_insert_scoped_checkpoints ON checkpoints
    FOR INSERT TO PUBLIC
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_update_scoped_checkpoints ON checkpoints
    FOR UPDATE TO PUBLIC
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_delete_scoped_checkpoints ON checkpoints
    FOR DELETE TO PUBLIC
    USING (tenant_id = current_setting('app.tenant_id', true));

CREATE POLICY tenant_select_all_quarantine ON quarantine
    FOR SELECT TO PUBLIC USING (true);
CREATE POLICY tenant_insert_scoped_quarantine ON quarantine
    FOR INSERT TO PUBLIC
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_update_scoped_quarantine ON quarantine
    FOR UPDATE TO PUBLIC
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
CREATE POLICY tenant_delete_scoped_quarantine ON quarantine
    FOR DELETE TO PUBLIC
    USING (tenant_id = current_setting('app.tenant_id', true));

-- =========================================================================
-- Tier 3.1 (D-AUDIT-1..8): append-only, hash-chained, per-tenant audit log.
-- See scripts/0008_add_audit_log.sql for the full rationale. Hash-bound fields
-- (`at`, `extra_canonical`, `hash_input`) are app-owned TEXT by design — do NOT
-- convert to JSONB/TIMESTAMPTZ (would false-positive the tamper walker, H2).
-- APPEND-ONLY: SELECT+INSERT grants only, no UPDATE/DELETE policy; the daemon
-- role MUST be a non-owner for that + FORCE RLS to hold.
-- =========================================================================
CREATE TABLE IF NOT EXISTS audit_log (
    tenant_id             VARCHAR(64)  NOT NULL,
    seq                   BIGINT       NOT NULL,
    run_id                VARCHAR(64)  NOT NULL,
    event_type            VARCHAR(48)  NOT NULL,
    event_seq             INTEGER      NOT NULL,
    round                 INTEGER,
    at                    TEXT         NOT NULL,
    workflow_class        TEXT         NOT NULL,
    workflow_version_hash VARCHAR(16),
    executor_model        VARCHAR(128) NOT NULL,
    reviewer_model        VARCHAR(128) NOT NULL,
    content_hash          CHAR(64)     NOT NULL,
    extra_canonical       TEXT         NOT NULL DEFAULT '{}',
    prev_hash             CHAR(64)     NOT NULL,
    hash_input            TEXT         NOT NULL,
    row_hash              CHAR(64)     NOT NULL,
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
        'run_started','run_completed','run_failed')),
    CONSTRAINT audit_idempotent        UNIQUE (tenant_id, run_id, event_seq)
);

CREATE INDEX IF NOT EXISTS idx_audit_tenant_seq ON audit_log (tenant_id, seq DESC);
CREATE INDEX IF NOT EXISTS idx_audit_run ON audit_log (tenant_id, run_id, seq);

ALTER TABLE audit_log ENABLE ROW LEVEL SECURITY;
ALTER TABLE audit_log FORCE  ROW LEVEL SECURITY;

CREATE POLICY audit_select_all ON audit_log
    FOR SELECT TO PUBLIC USING (true);
CREATE POLICY audit_insert_scoped ON audit_log
    FOR INSERT TO PUBLIC
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));
-- No UPDATE policy. No DELETE policy. Absence = denied under RLS (append-only).

-- Least-privilege role pattern. Replace 'daemon_user' with your role name.
-- The daemon connection MUST NOT use a superuser.
--
-- Run after table creation (commented to keep schema.sql idempotent on init):
--   GRANT SELECT, INSERT, UPDATE, DELETE ON checkpoints TO daemon_user;
--   GRANT SELECT, INSERT, UPDATE, DELETE ON quarantine TO daemon_user;
--   -- Tier 3.1 audit log is APPEND-ONLY: SELECT + INSERT only, never UPDATE/DELETE.
--   GRANT SELECT, INSERT ON audit_log TO daemon_user;
--   -- No GRANT TRUNCATE; no DDL; no other tables.
--   -- daemon_user MUST NOT own audit_log (append-only + FORCE RLS rely on non-owner).
--
-- For operator scripts (list_quarantined.py / requeue.py), prefer a separate
-- role with narrower grants:
--   GRANT SELECT ON quarantine, checkpoints TO operator_ro;
--   GRANT UPDATE (requeued_at) ON quarantine TO operator_rw;
--   -- Audit walker / compliance read (verify_audit_chain.py, reconcile_audit.py):
--   GRANT SELECT ON audit_log TO auditor_ro;
