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


needs_postgres = pytest.mark.skipif(
    asyncpg is None or _dsn() is None,
    reason="requires asyncpg + POSTGRES_DSN env var",
)


@pytest.fixture
async def pg_pool():
    import asyncpg as ap

    dsn = _dsn()
    assert dsn is not None
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
