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


@pytest.fixture
async def fresh_checkpoints_table(pg_pool):
    """Drop + recreate checkpoints table from schema.sql for each test."""
    async with pg_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS checkpoints CASCADE;")
        schema_sql = SCHEMA_FILE.read_text(encoding="utf-8")
        await conn.execute(schema_sql)
    yield
    async with pg_pool.acquire() as conn:
        await conn.execute("DROP TABLE IF EXISTS checkpoints CASCADE;")
