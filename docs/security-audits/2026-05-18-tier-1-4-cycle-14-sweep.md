# Tier 1.4 cycle-14 audit — schema migration scaffolding

**Date:** 2026-05-18
**Scope:** `core/durable/schema_migrations.py` + `examples/production/durable_postgres/scripts/migrate_schema.py` + `_migrate_helpers.py` + smoke tests + library mechanism tests. Advisor-revised lean cut: empty registry + chain primitive + synthetic smoke fixture.
**Dispatch:** inline structured walk (subagent dispatch unavailable in this session, same posture as cycles 12-13).
**Reviewer model:** self (Claude Opus 4.7, autonomous).
**Decisions audited:** D-SCHEMA-1..5.

---

## Verdict

**0 CRITICAL · 0 HIGH · 0 MEDIUM · 2 LOW (both accepted/documented)**

Scaffolding is sound. Library runtime fail-closed posture preserved. Tool is dry-run-default + forward-only + optimistic-CAS-guarded. Operator burden documented (post-migration reseal is required and noted in runbook + script docstring + commit).

---

## Check (a) — Library runtime fail-closed posture preserved

**Requirement:** `Checkpoint.from_dict` (`checkpoint.py:117`) and `ResumeToken.from_dict` (`token.py:61`) and `workflow.py:542` MUST still raise on `schema_version != CURRENT_SCHEMA_VERSION`. No runtime auto-migration fallback added.

**Evidence:**
- `schema_migrations.py` is a NEW file; no edits to `checkpoint.py`, `token.py`, or `workflow.py`. Grep confirms.
- Module docstring explicitly states the invariant: "the library runtime stays fail-closed... `chain_migrations` is invoked ONLY by the offline tool, never on the read hot-path."
- `chain_migrations` import does not appear in any library module other than its own definition.

**Posture:** PASS. Runtime continues to raise `SchemaVersionMismatch` on read; the only legitimate consumer of `chain_migrations` is the offline script.

---

## Check (b) — A10-H2 integrity invariant: post-migration reseal documented

**Requirement:** the migration tool rewrites bytes (changes `schema_version`, potentially other fields). The Tier 1.9 `integrity_tag` covers the canonical-JSON serialization of those bytes. A migrated-but-not-resealed row would fail tag verification on next read.

**Evidence:**
- `migrate_schema.py` docstring (lines 11-18): "After running, callers MUST run `reseal_all_checkpoints.py --apply` to recompute the A10-H2 integrity tag over the migrated bytes."
- `_migrate_all` final LOG line includes the explicit reminder: "after-migration operators MUST run reseal_all_checkpoints.py --apply".
- Runbook §8.1 step 5 added the reseal step between migrate and verify.

**Operator action checklist (per CLAUDE.md operator-actions-belong-in-a-file rule):** Yes — runbook §8.1 is the durable home; PR description is not load-bearing. Verb scan of `migrate_schema.py` docstring identifies: `run`, `recompute`, `verify` — all surface in the runbook procedure.

**Posture:** PASS (informational — migration is offline-only at v1 so no production row needs reseal yet; the runbook + docstring + log line ensure that when v2 lands operators have three reinforcing reminders).

---

## Check (c) — Dry-run is default

**Requirement:** D-SCHEMA-4 + matches `reseal_all_checkpoints.py` precedent.

**Evidence:**
- `_parse_args` (`migrate_schema.py:240-258`): `--dry-run` has `action="store_true", default=True`; `--apply` is the explicit opt-in inside a mutually-exclusive group; help text says "(default) scan + log; do not write".
- `_main` derives `apply = bool(args.apply)` — explicit, not negated.
- Sweep loop's write path is gated by `if not apply: ... continue` BEFORE any `write_if_unchanged` call.

**Posture:** PASS.

---

## Check (d) — D-SCHEMA-5 future-version abort works

**Requirement:** rows with `schema_version > target_version` abort the sweep before mutating anything.

**Evidence:**
- `_migrate_helpers.migrate_one_payload`: explicit `FutureVersionError` raise before any migration call when `from_version > target_version`.
- `_migrate_all` sweep loop has a SECOND defense-in-depth check on `row_version > target_version` BEFORE reading raw payload — guarantees abort happens with `run_id` in scope (good error message) and BEFORE the encrypted-read path that would raise a less-specific exception.
- `_main` rejects `--target-version > CURRENT_SCHEMA_VERSION` at argument time, so the tool refuses to attempt a migration to a version the library does not know about.
- Smoke test `test_future_version_row_aborts` asserts both the error type and message shape.
- `break` (not `continue`) on the future-version branch ensures partial-mutated DB is impossible.

**Posture:** PASS. Three reinforcing guards (helper-level, sweep-level, arg-level).

---

## Check (e) — No PHI in error messages

**Requirement:** error/log messages must not leak per-row sensitive content. Same posture as D-AEAD-3 (cipher decrypt failure shows 32-char hash prefix only).

**Evidence:**
- `MissingMigrationError` / `BrokenMigrationError` messages mention only the schema version numbers (integers).
- `FutureVersionError` includes `run_id` (already considered a non-sensitive identifier per existing project posture — appears in logs throughout the durable subsystem) and the version number. No payload content surfaces.
- `migrate_one_payload` extracts only `run_id` + `schema_version` from the payload for error context — never logs the full payload.
- `_migrate_all` LOG calls use `%s run_id=%s schema_version=%d` patterns — no payload interpolation.

**Posture:** PASS.

---

## LOW findings (accepted/documented)

### LOW-1: At v1 (empty REGISTRY), the migrate-script's payload reconstruction is a stub

**Location:** `migrate_schema.py:172-178` — when a row needs migration the script builds a minimal `payload = {"run_id": ..., "schema_version": ...}` dict rather than reconstructing the full Checkpoint fields.

**Why this is a LOW not a defect at v1:** the `row_version == target_version` short-circuit above means at v1 (REGISTRY empty + every healthy row already at v1) this stub is unreachable in production. The first real migration will need to refine this read shape to pull all encrypted/decoded fields. The stub is marked with a NOTE comment.

**Action:** when v2 lands, the same PR that adds `_v1_to_v2` to REGISTRY must extend the payload-reconstruction here. Tracked in `docs/NEXT_SESSION.md` as "first-real-migration follow-up".

### LOW-2: Smoke tests live in `examples/.../scripts/` and don't count toward library test total

**Location:** `examples/production/durable_postgres/scripts/test_migrate_schema_smoke.py`.

**Why accepted:** matches `test_reseal_smoke.py` precedent. Library `testpaths = ["tests"]` excludes the scripts dir intentionally — deployment-sibling tests shouldn't bloat the library matrix. Smoke tests are operator-side validation, run via `python -m pytest examples/production/durable_postgres/scripts/`.

**Action:** none — same pattern as the existing reseal smoke test.

---

## Coverage delta

- Library tests: 722 → 727 (+5: `test_schema_migrations.py`).
- Sibling smoke tests: +4 (`test_migrate_schema_smoke.py`, not in library count).

## Sign-off

Scaffolding ready to ship. First-real-migration follow-up tracked. Library runtime fail-closed posture verified preserved.
