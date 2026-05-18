# Schema migration tool — design (Tier 1.4, advisor-revised lean cut)

**Author:** Claude Opus 4.7 (autonomous, 2026-05-18)
**Driver:** `docs/production-readiness-gaps.md` §1.4
**Advisor revision:** original 4-5d scope was premature; no real v2 schema exists. Ship the *mechanism* + *convention doc* + *synthetic smoke-test fixture*. The first real migration lands when the first real schema change does.

---

## 1. Goal

Document the established convention (Tier 1.6 + Tier 1.9 both shipped without `CURRENT_SCHEMA_VERSION` bump by using "nullable field + deserializer exemption"). Define the path for when a non-additive change requires a bump. Ship scaffolding that exercises one synthetic v1→v2 migration as a smoke test — proving the mechanism works without inventing a real migration.

**Critical constraint (advisor item #1):** the migration tool runs OFFLINE. The runtime continues to raise on `schema_version != CURRENT_SCHEMA_VERSION` (per `checkpoint.py:117`, `token.py:61`, `workflow.py:542`). The tool walks rows, rewrites them; the workflow stays fail-closed at read time. This preserves A10-H2 integrity invariant.

---

## 2. The established convention (additive changes — NO bump needed)

Tier 1.6 added `Checkpoint.workflow_version_hash: str | None`. Tier 1.9 added `Checkpoint.integrity_tag: str | None`. Both:

1. Added the field as `dataclass` field with default `None`
2. Added the field name to the deserializer's missing-key exemption set
3. Left `CURRENT_SCHEMA_VERSION = 1` unchanged

This pattern works for: nullable adds. Legacy rows load with the field = None; the rest of the codebase tolerates None (warning + reseal on next write for Tier 1.9; pause-with-drift for Tier 1.6).

**Document this convention as the default path.** Schema bumps are for the cases this pattern can't handle.

## 3. When a schema bump IS required

Bump `CURRENT_SCHEMA_VERSION` when ANY of:

- **Rename a field** — legacy rows have the old key, new code looks for the new key, deserializer can't reconcile transparently
- **Drop a required field** — code paths still reference the dropped field
- **Change a field's type** in a non-coercible way (e.g., `str → int`)
- **Change semantics of an existing field** without renaming (silent semantic break is worse than rename)
- **Re-shape `rounds_history` entries** in a way that breaks per-entry consumers
- **Promote a nullable field to required** with no sane default

Adding a new nullable field, adding a new metric tag, or extending a free-form dict like `pause_context` does NOT require a bump.

## 4. Locked design choices

### D-SCHEMA-1: Registry lives in library, but ships EMPTY at v1

`core/durable/schema_migrations.py` ships as:

```python
"""Schema migrations registry. EMPTY at CURRENT_SCHEMA_VERSION=1.

Per docs/superpowers/specs/2026-05-18-schema-migration-design.md:
- Additive changes (nullable field + deserializer exemption) do NOT bump version
- When a bump becomes necessary, register the migration function here

The migration tool in examples/production/durable_postgres/scripts/migrate_schema.py
walks rows and applies registered migrations in order.

REGISTRY[N] applies to rows with schema_version=N to produce schema_version=N+1.
"""
from __future__ import annotations

from typing import Callable, Any

# Empty at v1. First entry lands when v2 is required.
# Example shape (for documentation only — do NOT uncomment):
# def _v1_to_v2(row: dict[str, Any]) -> dict[str, Any]:
#     row["new_field"] = _derive_from_old(row["old_field"])
#     del row["old_field"]
#     row["schema_version"] = 2
#     return row
# REGISTRY: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {1: _v1_to_v2}

REGISTRY: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


def chain_migrations(row: dict[str, Any], target_version: int) -> dict[str, Any]:
    """Apply registered migrations to bring row up to target_version.

    Idempotent: if row is already at target_version, returns unchanged.
    Raises if a required migration is missing from REGISTRY.
    """
    current = row.get("schema_version", 1)
    while current < target_version:
        if current not in REGISTRY:
            raise MissingMigrationError(
                f"No migration registered for schema_version={current} -> {current+1}"
            )
        row = REGISTRY[current](row)
        new_version = row.get("schema_version")
        if new_version != current + 1:
            raise BrokenMigrationError(
                f"Migration {current} -> {current+1} returned schema_version={new_version}"
            )
        current = new_version
    return row


class MissingMigrationError(Exception):
    """Raised when a row needs a migration that isn't registered."""


class BrokenMigrationError(Exception):
    """Raised when a migration function returns a row with the wrong schema_version."""
```

Why library-side (advisor item #3 reconsidered): the registry is small (one dict + one function); per-domain customization isn't a real concern (migrations are shape-level, not domain-level). Keeping it in `core/durable/` avoids forcing every operator to copy-paste the chain-migrations logic into their script. Tier 1.9's seam reasoning (Cipher Protocol = byte primitive vs AEAD-of-row = different abstraction) doesn't apply here — `chain_migrations` IS the right primitive.

### D-SCHEMA-2: Migration script lives in deployment

`examples/production/durable_postgres/scripts/migrate_schema.py` — uses `chain_migrations`, walks Postgres rows, applies, writes back with optimistic-concurrency guard. Same pattern as `reencrypt_all.py` + `reseal_all_checkpoints.py`.

### D-SCHEMA-3: Synthetic smoke test for the mechanism

`tests/unit/durable/test_schema_migrations.py` — does NOT depend on REGISTRY being non-empty. Tests:

1. Empty registry, row at v1, target v1 → no-op, row unchanged
2. Synthetic v1→v2 migration registered IN THE TEST (via monkeypatch), row at v1 → row at v2 with field added
3. Missing migration → `MissingMigrationError`
4. Broken migration (returns wrong version) → `BrokenMigrationError`
5. Multi-step v1→v2→v3 chains apply in order

When v2 actually lands, the test file gets a "real" migration test alongside; the synthetic monkeypatch remains as mechanism coverage.

### D-SCHEMA-4: --dry-run default for the deployment script

Per Slice B of Tier 1.9 (`reseal_all_checkpoints.py` precedent): `--dry-run` is default; `--apply` is explicit opt-in.

### D-SCHEMA-5: Migration tool refuses to run if any row uses a future version

If a row has `schema_version > CURRENT_SCHEMA_VERSION` (downgrade scenario — fresh row written by newer lib, then operator rolls back to older lib), the tool aborts with explicit error. Downgrade is OUT OF SCOPE — the tool migrates forward only.

---

## 5. Invariants

1. **Runtime stays fail-closed.** `Checkpoint.from_dict` still raises on version mismatch. The migration tool is the ONLY supported bypass.
2. **Forward-only.** Tool refuses to downgrade.
3. **Idempotent.** Re-running the tool on already-migrated rows is a no-op.
4. **Optimistic-concurrency-guarded.** Tool uses `WHERE updated_at = ...` (same pattern as `reseal_all_checkpoints.py`).
5. **Registry order = migration order.** v1→v2 must apply before v2→v3.

## 6. Attack surface

| Surface | Threat | Mitigation |
|---|---|---|
| Migration script with elevated DB perms | Insider runs unauthorized rewrite | Script requires explicit `--apply`; dry-run is default; runs under operator credential not daemon SA |
| Bad migration function | Mass data corruption | Smoke test asserts mechanism; per-migration testing required when v2 lands; dry-run diff lets operator review before apply |
| Concurrent runs | Race during migration | Optimistic-concurrency guard same as reseal script |
| Schema version forging | Insider sets row to v999 to skip migration | Tool aborts on `schema_version > CURRENT_SCHEMA_VERSION` (D-SCHEMA-5) |

## 7. File layout

```
src/adv_multi_agent/core/durable/
  schema_migrations.py    REGISTRY (empty) + chain_migrations() + 2 exceptions

tests/unit/durable/
  test_schema_migrations.py  5 mechanism tests + monkeypatched v1->v2 fixture

examples/production/durable_postgres/scripts/
  migrate_schema.py        CLI: --dry-run default, --apply explicit, optimistic-CAS

docs/runbooks/
  durable-operations.md    section flip: schema migration row REFERENCE-IMPL-PENDING -> OPERATIONAL (scaffolding only; first real migration lands with first real bump)
```

## 8. Decision rows

- D-SCHEMA-1: Registry in library, ships EMPTY at v1 (advisor-reconsidered)
- D-SCHEMA-2: Migration script in deployment, mirrors reseal/reencrypt pattern
- D-SCHEMA-3: Synthetic smoke test for mechanism, no premature v2 invention
- D-SCHEMA-4: --dry-run default (matches reseal_all_checkpoints precedent)
- D-SCHEMA-5: Forward-only; tool aborts on future-version rows

## 9. Out of scope

- Real v2 schema (lands when needed)
- Downgrade migrations
- Cross-cipher migration (existing `reencrypt_all.py` handles)
- Live-DB integration tests (operator owns)
- GUI / progress bars for the CLI

## 10. Effort

Single slice, ~0.5d:
- Library `schema_migrations.py` + 5 tests: 0.25d
- Migration script + dry-run/apply + smoke test: 0.15d
- Runbook flip + decision rows + cycle-14 audit + NEXT_SESSION refresh: 0.1d

**Total: 0.5d** (down from 4-5d in gaps doc; the savings come from NOT inventing a v2 schema).
