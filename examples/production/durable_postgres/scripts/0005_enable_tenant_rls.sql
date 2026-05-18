-- Tier 2.1a / D-TENANT-3: enable Row-Level Security on checkpoints + quarantine.
--
-- APPLY AFTER 0004 + after backfill. Order:
--   0004 (column + CHECK) -> backfill rows -> 0005 (this) -> 0006 (NOT NULL)
--
-- RLS policy model (D-TENANT-3 option a):
--   - SELECT is unscoped (USING true). Daemon scheduler poll lists paused
--     runs across all tenants. Acceptable because:
--       (a) Per-tenant cipher (Tier 2.1c) means cross-tenant SELECT only
--           leaks metadata (run_id, status, tenant_id, wake_at), not payloads.
--       (b) Tier 3.4 (tenant-shard scheduling) is the future path to
--           per-tenant SELECT scoping.
--   - INSERT/UPDATE/DELETE are scoped via current_setting('app.tenant_id').
--     Daemon code MUST set this GUC inside an explicit transaction
--     (`async with conn.transaction()`) before any DML. SET LOCAL semantics
--     require an active transaction — see store.py CI grep gate
--     (scripts/check_set_local_pattern.py).
--
-- SECURITY MODEL: the SELECT-all policy means daemon role compromise reads
-- all tenants' metadata. Per-tenant encryption (2.1c) is the durable defense;
-- this RLS layer prevents accidental cross-tenant WRITES (the higher-blast
-- mode), not READS. DBA break-glass via superuser still bypasses everything.

ALTER TABLE checkpoints ENABLE ROW LEVEL SECURITY;
ALTER TABLE quarantine  ENABLE ROW LEVEL SECURITY;

-- D-TENANT-3-FORCE (audit 2026-05-18 Q1): FORCE row security for table owner.
-- Without FORCE, the role that owns the table bypasses RLS even when
-- ENABLE ROW LEVEL SECURITY is on — operator running pg_dump or psql as
-- the owner role reads ALL tenants' rows without GUC. This is the daemon
-- BYPASSRLS hole at the role level.
--
-- INTENTIONALLY COMMENTED — must be run as a SEPARATE OPERATOR STEP
-- AFTER backfill (phase 2) AND AFTER the daemon role is split from the
-- migration role. Running this DURING the migration window would block
-- the migration script's backfill UPDATE because the script holds the
-- owner connection without a GUC set.
--
-- Operator runs this as a final hardening step. See runbook §5.6 phase 7.
--   ALTER TABLE checkpoints FORCE ROW LEVEL SECURITY;
--   ALTER TABLE quarantine  FORCE ROW LEVEL SECURITY;

-- =========================================================================
-- CHECKPOINTS policies
-- =========================================================================

-- SELECT: unscoped. Scheduler polls all tenants' paused rows.
DROP POLICY IF EXISTS tenant_select_all_checkpoints ON checkpoints;
CREATE POLICY tenant_select_all_checkpoints
    ON checkpoints
    FOR SELECT
    TO PUBLIC
    USING (true);

-- INSERT: row's tenant_id must match the GUC.
-- `current_setting('app.tenant_id', true)` returns NULL when GUC unset;
-- the equality predicate then evaluates NULL, RLS rejects the row. Fails closed.
DROP POLICY IF EXISTS tenant_insert_scoped_checkpoints ON checkpoints;
CREATE POLICY tenant_insert_scoped_checkpoints
    ON checkpoints
    FOR INSERT
    TO PUBLIC
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

-- UPDATE: USING filters which rows are visible-to-update; WITH CHECK
-- validates the new row. Both clauses enforce tenant match — defense in depth
-- against an UPDATE that would migrate a row's tenant_id mid-flight.
DROP POLICY IF EXISTS tenant_update_scoped_checkpoints ON checkpoints;
CREATE POLICY tenant_update_scoped_checkpoints
    ON checkpoints
    FOR UPDATE
    TO PUBLIC
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_delete_scoped_checkpoints ON checkpoints;
CREATE POLICY tenant_delete_scoped_checkpoints
    ON checkpoints
    FOR DELETE
    TO PUBLIC
    USING (tenant_id = current_setting('app.tenant_id', true));

-- =========================================================================
-- QUARANTINE policies (identical pattern)
-- =========================================================================

DROP POLICY IF EXISTS tenant_select_all_quarantine ON quarantine;
CREATE POLICY tenant_select_all_quarantine
    ON quarantine
    FOR SELECT
    TO PUBLIC
    USING (true);

DROP POLICY IF EXISTS tenant_insert_scoped_quarantine ON quarantine;
CREATE POLICY tenant_insert_scoped_quarantine
    ON quarantine
    FOR INSERT
    TO PUBLIC
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_update_scoped_quarantine ON quarantine;
CREATE POLICY tenant_update_scoped_quarantine
    ON quarantine
    FOR UPDATE
    TO PUBLIC
    USING (tenant_id = current_setting('app.tenant_id', true))
    WITH CHECK (tenant_id = current_setting('app.tenant_id', true));

DROP POLICY IF EXISTS tenant_delete_scoped_quarantine ON quarantine;
CREATE POLICY tenant_delete_scoped_quarantine
    ON quarantine
    FOR DELETE
    TO PUBLIC
    USING (tenant_id = current_setting('app.tenant_id', true));

-- =========================================================================
-- Verify policies installed (commented; operator runs as smoke check):
-- =========================================================================
--   SELECT tablename, policyname, cmd, qual, with_check
--   FROM   pg_policies
--   WHERE  tablename IN ('checkpoints', 'quarantine')
--   ORDER  BY tablename, cmd;
--
-- Expected: 4 policies per table = 8 rows.
