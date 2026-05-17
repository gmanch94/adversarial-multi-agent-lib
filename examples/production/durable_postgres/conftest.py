"""Expose DB fixtures for smoke_test.py at the durable_postgres/ level.

smoke_test.py lives one directory above tests/, so pytest cannot auto-discover
the fixtures in tests/conftest.py. This shim re-exports them so that running
    pytest examples/production/durable_postgres/smoke_test.py
finds pg_pool and fresh_checkpoints_table.
"""
from __future__ import annotations

# Re-export fixtures — pytest discovers them via this conftest.
from examples.production.durable_postgres.tests.conftest import (  # noqa: F401
    fresh_checkpoints_table,
    needs_postgres,
    pg_pool,
)
