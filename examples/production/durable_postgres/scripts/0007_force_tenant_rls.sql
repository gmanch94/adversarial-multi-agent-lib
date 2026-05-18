-- Tier 2.1d / D-TENANT-FORCE-RLS: enforce RLS on table owner.
--
-- ORDER: 0007 runs LAST in the multi-tenant migration sequence:
--   0004 (column + CHECK) -> backfill -> 0005 (RLS policies) -> 0006 (NOT NULL)
--   -> daemon role split from migration role -> 0007 (THIS)
--
-- WHY THIS IS REQUIRED:
--   Postgres exempts the table OWNER from RLS unless `FORCE ROW LEVEL
--   SECURITY` is set. If an operator runs `psql -f schema.sql` as the
--   daemon role (typical in dev/POC), the daemon BECOMES the owner and
--   every cross-tenant WITH CHECK silently passes. RLS becomes decorative.
--
--   Audit finding HIGH-1 (2026-05-18 LATE NIGHT review): without FORCE,
--   `cp.tenant_id="tenantB"` injected into a write bound for `tenantA`
--   succeeds — the headline invariant of Tier 2.1 fails.
--
-- OPERATOR PRECONDITIONS BEFORE RUNNING 0007:
--   1. 0004/0005/0006 have all been applied + backfill complete
--   2. The daemon application role is DIFFERENT from the table-owner role
--      (e.g., owner = `migration_role`, daemon = `app_role`).
--      If you must run daemon as owner: do NOT run this migration; instead
--      accept the BYPASSRLS exposure and document it in your threat model.
--   3. All long-running migration UPDATEs are complete — FORCE applies
--      immediately and would reject GUC-less DML mid-migration.
--
-- NO-OP SAFETY: ALTER ... FORCE is idempotent. Running 0007 twice does
-- not error.

ALTER TABLE checkpoints FORCE ROW LEVEL SECURITY;
ALTER TABLE quarantine  FORCE ROW LEVEL SECURITY;

-- Verify (operator smoke check):
--   SELECT relname, relrowsecurity, relforcerowsecurity
--   FROM   pg_class
--   WHERE  relname IN ('checkpoints', 'quarantine');
-- Expected: both rows show t,t.
