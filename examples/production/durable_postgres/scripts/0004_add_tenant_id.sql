-- Tier 2.1a / D-TENANT-1, D-TENANT-2: add tenant_id column for multi-tenant isolation.
--
-- Two-phase migration (advisor pass 2026-05-18 #2):
--   Phase 1 (this file): add NULLABLE column + CHECK constraint + index.
--                         Operators backfill rows AT THEIR OWN PACE.
--                         Single-tenant deployments use reserved tenant_id='_default'.
--   Phase 2 (0006_tenant_id_not_null.sql): flip column to NOT NULL.
--                         Migration FAILS if any row still has NULL — forces
--                         operators to backfill before flipping.
--
-- IMPORTANT: 0005_enable_tenant_rls.sql MUST be applied AFTER backfill but
-- BEFORE 0006. Order is: 0004 (this) -> backfill -> 0005 (RLS) -> 0006 (NOT NULL).
-- Operator runbook: docs/runbooks/durable-compliance.md §5.6.
--
-- Charset: ^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$ — mirrors run_id but ALSO allows
-- leading underscore, so reserved `_default` and `_legacy` tenant_ids validate.
-- Length cap 64 chars.
--
-- TRANSITIONAL STATE WARNING (D-TENANT-0):
-- Between this migration and 2.1c (per-tenant cipher) shipping, the deployment
-- is in "multi-tenant schema preparation". Daemon BYPASSRLS for poll + single
-- keyring for all payloads. NOT real multi-tenant isolation yet — do not
-- advertise as such until 2.1c lands.

ALTER TABLE checkpoints
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64);

ALTER TABLE checkpoints
    DROP CONSTRAINT IF EXISTS tenant_id_charset;
ALTER TABLE checkpoints
    ADD CONSTRAINT tenant_id_charset
    CHECK (tenant_id IS NULL OR tenant_id ~ '^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$');

-- Tenant_id on quarantine table follows same pattern. Quarantine is new in
-- Tier 2.4 — operators redeploying fresh from 2.4 onwards get tenant_id
-- column from day 0. Legacy 2.4 deployments backfill via operator runbook.
ALTER TABLE quarantine
    ADD COLUMN IF NOT EXISTS tenant_id VARCHAR(64);

ALTER TABLE quarantine
    DROP CONSTRAINT IF EXISTS quarantine_tenant_id_charset;
ALTER TABLE quarantine
    ADD CONSTRAINT quarantine_tenant_id_charset
    CHECK (tenant_id IS NULL OR tenant_id ~ '^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$');

-- Composite index: tenant-scoped poll hot path post-2.1a is
-- "SELECT ... WHERE status='paused' AND tenant_id=$1 ORDER BY wake_at".
-- Partial index restricted to paused rows keeps the index tight (only the
-- subset that's hot for the scheduler). status+tenant_id+wake_at order
-- matches the WHERE-clause prefix; PostgreSQL can range-scan wake_at within
-- (status='paused', tenant_id=$1).
CREATE INDEX IF NOT EXISTS idx_paused_tenant_wake
    ON checkpoints (tenant_id, wake_at NULLS LAST)
    WHERE status = 'paused';

-- Quarantine: active-row hot path is per-tenant for the list_quarantined script.
CREATE INDEX IF NOT EXISTS idx_quarantine_tenant_active
    ON quarantine (tenant_id, quarantined_at DESC)
    WHERE requeued_at IS NULL;

-- Backfill template (commented; operator runs after deciding tenant assignment):
--
--   -- Single-tenant deployment (recommended for legacy single-tenant operators):
--   UPDATE checkpoints SET tenant_id = '_default' WHERE tenant_id IS NULL;
--   UPDATE quarantine  SET tenant_id = '_default' WHERE tenant_id IS NULL;
--
--   -- Multi-tenant deployment (operator-specific mapping required):
--   UPDATE checkpoints SET tenant_id = CASE
--       WHEN run_id LIKE 'tenant-a-%' THEN 'tenant-a'
--       WHEN run_id LIKE 'tenant-b-%' THEN 'tenant-b'
--       ELSE '_default'
--   END WHERE tenant_id IS NULL;
--
-- After backfill: verify zero NULL rows before applying 0006:
--   SELECT COUNT(*) FROM checkpoints WHERE tenant_id IS NULL;  -- must be 0
--   SELECT COUNT(*) FROM quarantine  WHERE tenant_id IS NULL;  -- must be 0
