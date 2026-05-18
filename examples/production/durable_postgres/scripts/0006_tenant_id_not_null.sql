-- Tier 2.1a / D-TENANT-1 phase 2: flip tenant_id to NOT NULL.
--
-- APPLY AFTER backfill is complete. The ALTER TABLE will FAIL if any row
-- still has tenant_id IS NULL — that is intentional. Re-run backfill, then
-- re-run this migration.
--
-- Verify zero NULL rows first:
--   SELECT COUNT(*) FROM checkpoints WHERE tenant_id IS NULL;  -- must be 0
--   SELECT COUNT(*) FROM quarantine  WHERE tenant_id IS NULL;  -- must be 0

ALTER TABLE checkpoints ALTER COLUMN tenant_id SET NOT NULL;
ALTER TABLE quarantine  ALTER COLUMN tenant_id SET NOT NULL;

-- After this migration, the partial CHECK constraint that allowed NULL
-- (added in 0004) is logically redundant but harmless. Drop + re-add as
-- pure pattern constraint for clarity:
ALTER TABLE checkpoints DROP CONSTRAINT IF EXISTS tenant_id_charset;
ALTER TABLE checkpoints
    ADD CONSTRAINT tenant_id_charset
    CHECK (tenant_id ~ '^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$');

ALTER TABLE quarantine DROP CONSTRAINT IF EXISTS quarantine_tenant_id_charset;
ALTER TABLE quarantine
    ADD CONSTRAINT quarantine_tenant_id_charset
    CHECK (tenant_id ~ '^[a-zA-Z0-9_][a-zA-Z0-9_-]{0,63}$');
