"""Manual live-integration demo for the Postgres reference deployment.

REAL API calls — costs real money per invocation. Uses synthetic
de-identified ClinicalTrial inputs. Not a test; prints RunOutcome for
human inspection.

Run via:
    docker compose up -d         # bring up postgres + scheduler
    docker compose exec scheduler python caller.py

Smoke-correctness assertions live in smoke_test.py (fake agents, no API
cost). This file is the live-integration sanity check.
"""
from __future__ import annotations

import asyncio
import os

from adv_multi_agent.core.config import Config
from adv_multi_agent.core.durable import DurableWorkflow
from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility import (
    TrialEligibilityRequest,
)


_DISCLAIMER = """
========================================================================
WARNING: this script makes REAL model API calls. Each run costs real
money. Synthetic de-identified inputs only. No PHI.
========================================================================
"""


_SYNTHETIC_REQUEST = TrialEligibilityRequest(
    trial_id="DEMO-001",
    protocol_summary=(
        "Phase II open-label study of investigational compound X in "
        "subjects with biomarker-positive condition Y. Inclusion: age 18-75, "
        "ECOG 0-1, biomarker confirmed by central lab. Exclusion: prior "
        "compound X exposure, active infection, organ dysfunction. "
        "NOTE: labs pending — biomarker confirmation awaited."
    ),
    patient_profile=(
        "Synthetic subject. Age 52, ECOG 0, no prior X exposure. "
        "No active infection. Baseline labs ordered, pending."
    ),
    biomarker_status="Pending central lab confirmation",
    prior_treatments="Standard of care line 1 (12 months); progression confirmed",
    competing_risks="None identified",
    site_context="Academic medical center, IRB-approved site",
)


async def main() -> None:
    # F-M-04: refuse to run outside the scheduler container; prevents
    # accidental execution against developer's host environment.
    # A8-L-03: dropped the inline "Set DURABLE_INSIDE_CONTAINER=1 to bypass"
    # hint. Helpful-looking error messages that hand the reader the bypass
    # token defeat the fence (same shape as L-PC-5). Operators that need
    # an out-of-container run path should add an explicit dev-only entry
    # to the README — not learn the bypass from a SystemExit message.
    if not os.environ.get("DURABLE_INSIDE_CONTAINER"):
        raise SystemExit(
            "ERROR: caller.py must run inside the scheduler container.\n"
            "Invoke via: docker compose exec scheduler python caller.py\n"
            "See README.md for the full quickstart."
        )

    print(_DISCLAIMER)
    print("Constructing DurableWorkflow against running daemon's store...")
    print("(See daemon.py for the actual wiring; this is the start/resume harness.)")
    print()

    # In a real caller, you'd import the daemon's store + lock directly.
    # For demo purposes, we expect the daemon container to be running.
    from .cipher import FernetCipher
    from .daemon import load_config_from_env
    from .lock import PostgresAdvisoryLock
    from .store import PostgresCheckpointStore
    from adv_multi_agent.core.durable import EncryptedCheckpointStore
    from adv_multi_agent.healthcare.workflows.clinical_trial_eligibility_durable import (
        ClinicalTrialEligibilityDurableWorkflow,
    )

    import asyncpg
    cfg = load_config_from_env()  # DaemonConfig (F-H-07)
    lock_pool = await asyncpg.create_pool(
        cfg.postgres_dsn, min_size=1, max_size=2,
    )
    query_pool = await asyncpg.create_pool(
        cfg.postgres_dsn, min_size=1, max_size=2,
    )
    try:
        agent_cfg = Config(
            anthropic_api_key=cfg.anthropic_api_key,
            openai_api_key=cfg.openai_api_key,
        )
        cipher = FernetCipher(keys=list(cfg.fernet_keys))
        store = EncryptedCheckpointStore(
            inner=PostgresCheckpointStore(query_pool),
            cipher=cipher,
        )
        lock = PostgresAdvisoryLock(lock_pool)

        inner = ClinicalTrialEligibilityDurableWorkflow(config=agent_cfg)
        durable = DurableWorkflow(
            inner=inner,
            config=agent_cfg,
            checkpoint_store=store,
            run_lock=lock,
        )

        print("Starting run (request mentions 'labs pending' → expect pause at gate 1)")
        outcome = await durable.start(_SYNTHETIC_REQUEST)
        print(f"Outcome: status={outcome.status} pause_reason={outcome.pause_reason}")
        print(f"Token: {outcome.token}")
        print()
        print("To resume: edit synthetic request to remove 'labs pending', then:")
        print("  outcome2 = await durable.resume(token, fresh_inputs=updated_request)")
    finally:
        await lock_pool.close()
        await query_pool.close()


if __name__ == "__main__":
    asyncio.run(main())
