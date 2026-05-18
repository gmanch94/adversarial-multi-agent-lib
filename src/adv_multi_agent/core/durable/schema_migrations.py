"""Schema migrations registry. EMPTY at CURRENT_SCHEMA_VERSION=1.

Per docs/superpowers/specs/2026-05-18-schema-migration-design.md (Tier 1.4):

The established convention for non-breaking schema evolution is
**additive-only**:

1. Add the new field to the dataclass with default ``None``.
2. Add the field name to the deserializer's missing-key exemption set
   (see ``_checkpoint_from_json`` in ``checkpoint.py``).
3. Leave ``CURRENT_SCHEMA_VERSION`` unchanged.

Tier 1.6 (``workflow_version_hash``) and Tier 1.9 (``integrity_tag``) both
shipped under this convention and are the canonical references for future
additive changes.

A ``CURRENT_SCHEMA_VERSION`` bump is required ONLY when the change cannot be
expressed additively — rename a field, drop a required field, change a
field's type non-coercibly, change a field's semantics without renaming,
re-shape ``rounds_history`` entries in a way that breaks per-entry
consumers, or promote a nullable field to required with no sane default.

When a bump becomes necessary:

* Define a migration function ``def _vN_to_vN_plus_1(row: dict) -> dict``
  that mutates the row in-place (or returns a new dict) and sets
  ``row["schema_version"] = N + 1``.
* Register it in ``REGISTRY`` keyed by the SOURCE version ``N``.
* The offline migration tool in
  ``examples/production/durable_postgres/scripts/migrate_schema.py`` walks
  every checkpoint row and calls ``chain_migrations`` to bring it up to
  ``CURRENT_SCHEMA_VERSION``.

**Critical invariant (spec §5 #1, D-SCHEMA-1):** the library runtime stays
fail-closed. ``Checkpoint.from_dict`` (``checkpoint.py``) and
``ResumeToken.from_dict`` (``token.py``) MUST continue to raise on version
mismatch. ``chain_migrations`` is invoked ONLY by the offline tool, never
on the read hot-path. This preserves the A10-H2 integrity posture: a row
mutated by the migration tool must be resealed afterward via
``reseal_all_checkpoints.py``.
"""
from __future__ import annotations

from typing import Any, Callable

# Empty at v1. First entry lands when v2 is required.
# Example shape (for documentation only — do NOT uncomment):
#
#   def _v1_to_v2(row: dict[str, Any]) -> dict[str, Any]:
#       row["new_field"] = _derive_from_old(row["old_field"])
#       del row["old_field"]
#       row["schema_version"] = 2
#       return row
#
#   REGISTRY: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {
#       1: _v1_to_v2,
#   }
REGISTRY: dict[int, Callable[[dict[str, Any]], dict[str, Any]]] = {}


class MissingMigrationError(Exception):
    """A row needs a migration from version N to N+1 that isn't registered."""


class BrokenMigrationError(Exception):
    """A registered migration returned a row with an unexpected schema_version."""


def chain_migrations(row: dict[str, Any], target_version: int) -> dict[str, Any]:
    """Apply registered migrations to bring ``row`` up to ``target_version``.

    Idempotent: if ``row["schema_version"] >= target_version`` the row is
    returned unchanged. (Downgrade is out of scope — the migration tool
    aborts on rows with ``schema_version > CURRENT_SCHEMA_VERSION`` before
    calling here, per D-SCHEMA-5.)

    Raises:
        MissingMigrationError: a migration from version N to N+1 is needed
            but not registered.
        BrokenMigrationError: a registered migration returned a row whose
            ``schema_version`` is not exactly source + 1.
    """
    current = int(row.get("schema_version", 1))
    while current < target_version:
        migration = REGISTRY.get(current)
        if migration is None:
            raise MissingMigrationError(
                f"no migration registered for schema_version={current} "
                f"-> {current + 1}"
            )
        row = migration(row)
        new_version = row.get("schema_version")
        if new_version != current + 1:
            raise BrokenMigrationError(
                f"migration {current} -> {current + 1} returned "
                f"schema_version={new_version!r}"
            )
        current = new_version
    return row
