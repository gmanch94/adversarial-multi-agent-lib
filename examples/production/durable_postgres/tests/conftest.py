"""Pytest fixtures for DB-backed tests.

Skip-by-default when POSTGRES_DSN env var is not set. Bring up local
Postgres via `docker compose up postgres` from the durable_postgres dir.
"""
from __future__ import annotations

import os
import pathlib

import pytest

try:
    import asyncpg  # noqa: F401
except ImportError:
    asyncpg = None  # type: ignore


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]
SCHEMA_FILE = PROJECT_ROOT / "schema.sql"


def _dsn() -> str | None:
    return os.environ.get("POSTGRES_DSN")


# A8-M-08: refuse to run DROP-bearing fixtures against a non-test DSN.
# fresh_checkpoints_table executes `DROP TABLE checkpoints CASCADE` — if a
# developer points POSTGRES_DSN at staging/production and runs pytest, every
# paused run gets erased. Guard: DSN must be obviously a test target.
_TEST_HOST_ALLOWLIST = ("localhost", "127.0.0.1", "::1")


def _is_test_dsn(dsn: str) -> bool:
    lowered = dsn.lower()
    if "test" in lowered:
        return True
    return any(f"@{h}" in lowered or f"//{h}" in lowered for h in _TEST_HOST_ALLOWLIST)


needs_postgres = pytest.mark.skipif(
    asyncpg is None or _dsn() is None,
    reason="requires asyncpg + POSTGRES_DSN env var",
)


@pytest.fixture
async def pg_pool():
    import asyncpg as ap

    dsn = _dsn()
    assert dsn is not None
    if not _is_test_dsn(dsn):
        raise RuntimeError(
            "Refusing DROP-bearing fixtures against a non-test POSTGRES_DSN. "
            "Host must be localhost/127.0.0.1/::1 OR the DSN must contain the "
            "substring 'test' (e.g. db name 'durable_test'). Set DSN to a test "
            "target and rerun. Current host segment: "
            f"{dsn.split('@', 1)[-1]!r}."
        )
    pool = await ap.create_pool(dsn, min_size=1, max_size=5)
    yield pool
    await pool.close()


_RLS_TEST_ROLE = "durable_rls_test"
_RLS_TEST_PW = "rls_test_pw"  # test-only, localhost throwaway DB — not a secret


@pytest.fixture
async def nonsuper_pool(pg_pool, fresh_checkpoints_table):
    """A NOSUPERUSER, non-owner pool with full DML grants on checkpoints +
    quarantine, so the tenant-RLS policies actually bind.

    Superusers bypass RLS by design (even FORCE RLS), and the throwaway
    postgres image's connecting role is a superuser — so RLS-enforcement tests
    run against `pg_pool` prove nothing (the WITH CHECK never fires). This
    fixture provisions a real non-super, non-owner role — the same mechanism
    test_audit_sink_pg uses — so the four RLS tests exercise the real layer-2
    threat instead of a no-op.

    Grant discipline (advisor 2026-07-24): each RLS test pairs a same-tenant
    positive control with the cross-tenant negative on THIS role. An RLS
    WITH-CHECK rejection and a missing table grant both surface as
    InsufficientPrivilegeError (42501); only a passing positive control on the
    same role proves the negative failed because of RLS, not a grant gap.

    Depends on fresh_checkpoints_table so grants land on the freshly-created
    tables; the pool closes in teardown BEFORE fresh_checkpoints_table drops
    them CASCADE (fixture finalizers run in reverse setup order).
    """
    import asyncpg as ap
    from urllib.parse import urlparse

    async with pg_pool.acquire() as conn:
        await conn.execute(
            "DO $$ BEGIN IF NOT EXISTS (SELECT FROM pg_roles WHERE "
            f"rolname='{_RLS_TEST_ROLE}') THEN CREATE ROLE {_RLS_TEST_ROLE} "
            f"LOGIN PASSWORD '{_RLS_TEST_PW}' NOSUPERUSER; END IF; END $$;"
        )
        await conn.execute(
            "GRANT SELECT, INSERT, UPDATE, DELETE ON checkpoints, quarantine "
            f"TO {_RLS_TEST_ROLE}"
        )
    dsn = _dsn()
    assert dsn is not None
    u = urlparse(dsn)
    pool = await ap.create_pool(
        user=_RLS_TEST_ROLE,
        password=_RLS_TEST_PW,
        host=u.hostname,
        port=u.port,
        database=u.path.lstrip("/"),
        min_size=1,
        max_size=3,
    )
    try:
        yield pool
    finally:
        await pool.close()


@pytest.fixture
async def fresh_checkpoints_table(pg_pool):
    """Drop + recreate checkpoints AND quarantine tables from schema.sql.

    D-TENANT-1 / Tier 2.1a: schema.sql now creates both tables + RLS policies.
    Both must be dropped CASCADE to clear stale rows + policies between tests.
    """
    async with pg_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS checkpoints CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS quarantine CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS audit_log CASCADE;")
        schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
        await conn.execute(schema_sql)
    yield
    async with pg_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS checkpoints CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS quarantine CASCADE;")
        await conn.execute("DROP TABLE IF EXISTS audit_log CASCADE;")
