"""Tier 2.1d / HIGH-1 audit gate — verify FORCE ROW LEVEL SECURITY is
declared on every multi-tenant table in BOTH `schema.sql` (fresh-deploy
path) and the migration sequence (`scripts/0007_force_tenant_rls.sql`,
existing-deploy upgrade path).

Without FORCE, the table-owner role bypasses RLS. CI must reject any
change that removes FORCE coverage.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

_HERE = Path(__file__).resolve().parent.parent  # examples/production/durable_postgres
_SCHEMA = _HERE / "schema.sql"
_FORCE_MIGRATION = _HERE / "scripts" / "0007_force_tenant_rls.sql"

_TENANT_TABLES = ("checkpoints", "quarantine")


def _force_statements(sql: str) -> set[str]:
    """Return the set of table names with FORCE RLS declared in sql."""
    pattern = re.compile(
        r"ALTER\s+TABLE\s+(\w+)\s+FORCE\s+ROW\s+LEVEL\s+SECURITY",
        re.IGNORECASE,
    )
    return {m.group(1).lower() for m in pattern.finditer(sql)}


@pytest.mark.parametrize("table", _TENANT_TABLES)
def test_schema_sql_forces_rls(table: str) -> None:
    sql = _SCHEMA.read_text(encoding="utf-8")
    forced = _force_statements(sql)
    assert table in forced, (
        f"{table!r} missing FORCE ROW LEVEL SECURITY in schema.sql — "
        f"table-owner role would bypass RLS (HIGH-1 audit finding). "
        f"Forced tables found: {sorted(forced)!r}"
    )


@pytest.mark.parametrize("table", _TENANT_TABLES)
def test_migration_0007_forces_rls(table: str) -> None:
    assert _FORCE_MIGRATION.exists(), (
        f"Migration {_FORCE_MIGRATION.name} missing — existing-deploy "
        f"upgrade path for FORCE RLS not provided."
    )
    sql = _FORCE_MIGRATION.read_text(encoding="utf-8")
    forced = _force_statements(sql)
    assert table in forced, (
        f"{table!r} missing FORCE in 0007 migration; forced tables: "
        f"{sorted(forced)!r}"
    )


def test_migration_0007_runs_after_not_null() -> None:
    """0007 must sort AFTER 0006 (NOT NULL flip) by filename prefix so the
    operator's natural-sort `psql -f scripts/*.sql` ordering is correct."""
    files = sorted((_HERE / "scripts").glob("000[4-9]*.sql"))
    names = [f.name for f in files]
    assert names == [
        "0004_add_tenant_id.sql",
        "0005_enable_tenant_rls.sql",
        "0006_tenant_id_not_null.sql",
        "0007_force_tenant_rls.sql",
    ], f"Migration ordering broken: {names}"
