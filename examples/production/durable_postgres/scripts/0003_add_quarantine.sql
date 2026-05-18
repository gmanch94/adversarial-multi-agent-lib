-- Tier 2.4: quarantine / dead-letter table.
--
-- Library scheduler keeps an in-memory quarantine set (SchedulerDaemon._quarantine)
-- that is wiped on daemon restart. This sibling-only table gives operators
-- durable visibility + a requeue handle. The sibling QuarantineSync task
-- (quarantine.py) snapshots the in-memory set each poll, INSERTs new entries,
-- and processes UPDATE requeued_at => discard from in-memory.
--
-- Idempotent: safe to re-run.
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

-- A14-M-01: index favors the operator-facing list_quarantined hot path.
CREATE INDEX IF NOT EXISTS idx_quarantine_active
    ON quarantine (quarantined_at DESC)
    WHERE requeued_at IS NULL;
