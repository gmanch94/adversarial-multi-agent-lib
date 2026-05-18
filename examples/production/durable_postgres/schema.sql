-- Reference checkpoints schema for examples/production/durable_postgres/.
-- See docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md §4.2
--
-- Migration sequence (apply in order on existing deployments):
--   0001 = initial schema (this file as of 2026-05-16; no separate file)
--   0002 = scripts/0002_add_integrity_tag.sql (Tier 1.9 / A10-H2 closure)
--   0003 = scripts/0003_add_quarantine.sql  (Tier 2.4 / quarantine + dead-letter)
--
-- Fresh installs run this file once; it includes every column from every
-- migration so a clean DB never needs the 000N_*.sql files.

CREATE TABLE IF NOT EXISTS checkpoints (
    run_id           VARCHAR(64) PRIMARY KEY,
    schema_version   INTEGER NOT NULL,
    status           VARCHAR(32) NOT NULL,
    wake_at          TIMESTAMPTZ,
    workflow_class   TEXT NOT NULL,
    payload          BYTEA NOT NULL,
    integrity_tag    TEXT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT run_id_charset CHECK (run_id ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$'),
    CONSTRAINT workflow_class_length CHECK (char_length(workflow_class) <= 512)
    -- F-M-07: payload is BYTEA NOT NULL. Smallest valid JSON object is "{}"
    -- (2 bytes). If a future migration adds CHECK (length(payload) > N),
    -- N must be <= 2 OR the migration must rewrite legacy rows.
    --
    -- A10-H2 (Tier 1.9): integrity_tag is a denormalized mirror of the value
    -- inside the serialized payload. The library does NOT read this column;
    -- it exists only so the reseal_all_checkpoints.py script can scan for
    -- legacy rows (integrity_tag IS NULL) via the partial index below.
);

-- Partial index supports the hot list_paused query.
CREATE INDEX IF NOT EXISTS idx_paused_wake
    ON checkpoints (wake_at NULLS LAST)
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
    quarantined_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    failure_count    INTEGER NOT NULL,
    reason           VARCHAR(32) NOT NULL,
    requeued_at      TIMESTAMPTZ,
    requeue_count    INTEGER NOT NULL DEFAULT 0,
    CONSTRAINT quarantine_run_id_charset CHECK (run_id ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$'),
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

-- Least-privilege role pattern. Replace 'daemon_user' with your role name.
-- The daemon connection MUST NOT use a superuser.
--
-- Run after table creation (commented to keep schema.sql idempotent on init):
--   GRANT SELECT, INSERT, UPDATE, DELETE ON checkpoints TO daemon_user;
--   GRANT SELECT, INSERT, UPDATE, DELETE ON quarantine TO daemon_user;
--   -- No GRANT TRUNCATE; no DDL; no other tables.
--
-- For operator scripts (list_quarantined.py / requeue.py), prefer a separate
-- role with narrower grants:
--   GRANT SELECT ON quarantine, checkpoints TO operator_ro;
--   GRANT UPDATE (requeued_at) ON quarantine TO operator_rw;
