-- Tier 1.9 / A10-H2: add integrity_tag column for full-Checkpoint AEAD.
--
-- The library stores integrity_tag inside the JSON-serialized `payload`
-- column. This denormalized column is an OPERATIONAL aid only: it lets the
-- reseal_all_checkpoints.py script scan for legacy rows (integrity_tag IS
-- NULL) via a partial index without deserializing every payload.
--
-- The store does NOT read or write this column directly; it stays in sync
-- because the reseal script (and a future store-side trigger, if desired)
-- mirrors the value from the deserialized Checkpoint.integrity_tag field.
--
-- Idempotent: safe to re-run.
ALTER TABLE checkpoints
    ADD COLUMN IF NOT EXISTS integrity_tag TEXT NULL;

-- Partial index supports the reseal script's pending-row scan.
CREATE INDEX IF NOT EXISTS checkpoints_integrity_tag_null_idx
    ON checkpoints (run_id)
    WHERE integrity_tag IS NULL;
