"""Rotation completion test (smoke test #15 in spec §2.6).

Writes rows under key A -> rotate to [B, A] -> run reencrypt -> assert all
rows decrypt under [B] alone.
"""
from __future__ import annotations

import pytest
from cryptography.fernet import Fernet

from examples.production.durable_postgres.tests.conftest import needs_postgres


pytestmark = [pytest.mark.asyncio, needs_postgres]


async def test_reencrypt_completes_rotation(pg_pool, fresh_checkpoints_table):
    from adv_multi_agent.core.durable import EncryptedCheckpointStore
    from adv_multi_agent.core.durable.checkpoint import Checkpoint

    from examples.production.durable_postgres.cipher import FernetCipher
    from examples.production.durable_postgres.store import PostgresCheckpointStore
    from examples.production.durable_postgres.scripts.reencrypt_all import (
        reencrypt_all,
    )

    key_a = Fernet.generate_key()
    key_b = Fernet.generate_key()

    # Phase 1: write 3 rows under key A
    cipher_a = FernetCipher(keys=[key_a])
    store_a = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher_a,
    )
    for i in range(3):
        cp = Checkpoint(
            run_id=f"rot-{i:03d}",
            tenant_id="_default",
            schema_version=1,
            status="paused",
            round=1,
            rounds_history=[{"r": 1}],
            last_request_json='{"x": 1}',
            pause_reason="rolling_data",
            pause_context={},
            budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
            pinned_executor_model="claude-opus-4-7",
            pinned_reviewer_model="gpt-4o",
            wake_at=None,  # v4: workflow_class not on Checkpoint
            created_at="2026-05-16T12:00:00Z",
            updated_at="2026-05-16T12:00:00Z",
        )
        await store_a.write(cp)

    # Phase 2: rotate to [B, A] and re-encrypt
    cipher_rot = FernetCipher(keys=[key_b, key_a])
    store_rot = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher_rot,
    )
    count = await reencrypt_all(store_rot, pg_pool)
    assert count == 3

    # Phase 3: drop key A, read with key B alone -- must succeed
    cipher_b_only = FernetCipher(keys=[key_b])
    store_b = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher_b_only,
    )
    for i in range(3):
        loaded = await store_b.read(f"rot-{i:03d}")
        assert loaded.run_id == f"rot-{i:03d}"


async def test_reencrypt_is_idempotent(pg_pool, fresh_checkpoints_table):
    from adv_multi_agent.core.durable import EncryptedCheckpointStore
    from adv_multi_agent.core.durable.checkpoint import Checkpoint

    from examples.production.durable_postgres.cipher import FernetCipher
    from examples.production.durable_postgres.store import PostgresCheckpointStore
    from examples.production.durable_postgres.scripts.reencrypt_all import (
        reencrypt_all,
    )

    key_a = Fernet.generate_key()
    cipher = FernetCipher(keys=[key_a])
    store = EncryptedCheckpointStore(
        inner=PostgresCheckpointStore(pg_pool), cipher=cipher,
    )
    cp = Checkpoint(
        run_id="idem-001",
        tenant_id="_default",
        schema_version=1,
        status="paused",
        round=1,
        rounds_history=[],
        last_request_json="{}",
        pause_reason=None,
        pause_context={},
        budget_used={"tokens_in": 0, "tokens_out": 0, "usd_spent": 0.0},
        pinned_executor_model="m1",
        pinned_reviewer_model="m2",
        wake_at=None,  # v4: workflow_class not on Checkpoint
        created_at="2026-05-16T12:00:00Z",
        updated_at="2026-05-16T12:00:00Z",
    )
    await store.write(cp)
    # Re-encrypt twice; second call must not error
    c1 = await reencrypt_all(store, pg_pool)
    c2 = await reencrypt_all(store, pg_pool)
    assert c1 == 1 and c2 == 1
