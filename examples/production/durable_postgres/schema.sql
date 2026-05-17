-- Reference checkpoints schema for examples/production/durable_postgres/.
-- See docs/superpowers/specs/2026-05-16-prod-postgres-deployment-design.md §4.2

CREATE TABLE IF NOT EXISTS checkpoints (
    run_id           VARCHAR(64) PRIMARY KEY,
    schema_version   INTEGER NOT NULL,
    status           VARCHAR(32) NOT NULL,
    wake_at          TIMESTAMPTZ,
    workflow_class   TEXT NOT NULL,
    payload          BYTEA NOT NULL,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CONSTRAINT run_id_charset CHECK (run_id ~ '^[a-zA-Z0-9][a-zA-Z0-9-]{0,63}$'),
    CONSTRAINT workflow_class_length CHECK (char_length(workflow_class) <= 512)
    -- F-M-07: payload is BYTEA NOT NULL. Smallest valid JSON object is "{}"
    -- (2 bytes). If a future migration adds CHECK (length(payload) > N),
    -- N must be <= 2 OR the migration must rewrite legacy rows.
);

-- Partial index supports the hot list_paused query.
CREATE INDEX IF NOT EXISTS idx_paused_wake
    ON checkpoints (wake_at NULLS LAST)
    WHERE status = 'paused';

-- Least-privilege role pattern. Replace 'daemon_user' with your role name.
-- The daemon connection MUST NOT use a superuser.
--
-- Run after table creation (commented to keep schema.sql idempotent on init):
--   GRANT SELECT, INSERT, UPDATE, DELETE ON checkpoints TO daemon_user;
--   -- No GRANT TRUNCATE; no DDL; no other tables.
