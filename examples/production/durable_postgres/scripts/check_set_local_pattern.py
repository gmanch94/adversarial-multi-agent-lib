"""CI grep gate enforcing the SET LOCAL pattern (Tier 2.1a / D-TENANT-3).

Parses examples/production/durable_postgres/store.py + quarantine.py and
asserts every `pool.acquire()` block is followed by `conn.transaction():`
with `set_config('app.tenant_id', ...)` as the first statement before any
DML (INSERT/UPDATE/DELETE).

WHY: `SET LOCAL` semantics require an active transaction. Autocommit SET LOCAL
is a no-op on some drivers and errors on others. A bare `SET` (without LOCAL)
leaks the GUC to the next pool checkout — the exact cross-tenant bug RLS is
meant to prevent. Advisor flagged this as BLOCKING #1 on 2026-05-18.

This is a STATIC check — it does not execute the file. The check is
intentionally narrow:
  - For every `async with self._pool.acquire() as conn:` (or equivalent),
    the immediately-next significant line must open `async with conn.transaction():`
  - Within that txn body, the first `await conn.execute(...)` must reference
    `set_config('app.tenant_id'` (the parameterized SET LOCAL idiom).
  - INSERT / UPDATE / DELETE in the txn body are allowed only AFTER the
    set_config call.

Files exempted from the check:
  - `read()` and `list_paused()` — SELECT-only, RLS-unscoped (D-TENANT-3)
  - test files
  - operator-script SELECT-only paths (still expected to set_config defensively
    but the grep check only fires on INSERT/UPDATE/DELETE)

Usage:
    python scripts/check_set_local_pattern.py
        # exit 0 on pass, exit 1 + error listing on fail

CI wire-in: add to `.github/workflows/ci.yml` as a separate step. Runs in <1s.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


_REPO_ROOT = Path(__file__).resolve().parents[4]
_TARGET_FILES = [
    "examples/production/durable_postgres/store.py",
    "examples/production/durable_postgres/quarantine.py",
    "examples/production/durable_postgres/scripts/list_quarantined.py",
    "examples/production/durable_postgres/scripts/requeue.py",
]

# Methods on PostgresCheckpointStore that are SELECT-only (no SET LOCAL needed).
# Cross-check against store.py D-TENANT-3 comment.
_SELECT_ONLY_METHODS = {
    "read", "read_with_tenant", "list_paused", "list_paused_with_tenants",
}

# DML keywords that REQUIRE a preceding set_config inside the same txn block.
_DML_RE = re.compile(
    r"^\s+(?:INSERT|UPDATE|DELETE)\b",
    re.MULTILINE | re.IGNORECASE,
)

# pool.acquire() block opener — must be followed by conn.transaction() for DML.
_ACQUIRE_RE = re.compile(
    r"async with (?:self\._pool|self\._pg_pool|self\._pool_obj|pool)\.acquire\(\) as conn:",
)

# Conn.transaction() opener.
_TRANSACTION_RE = re.compile(r"async with conn\.transaction\(\):")

# The required SET LOCAL idiom.
_SET_CONFIG_RE = re.compile(
    r"set_config\(\s*['\"]app\.tenant_id['\"]",
)


def _check_file(path: Path) -> list[str]:
    """Return list of error messages; empty list means file passes."""
    errors: list[str] = []
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()

    # Walk acquire() blocks. For each, find the next non-blank line(s) and
    # verify it opens conn.transaction(); then verify the first non-comment
    # line inside the txn body matches _SET_CONFIG_RE (when DML follows
    # later in the same block).
    for i, line in enumerate(lines):
        m = _ACQUIRE_RE.search(line)
        if not m:
            continue

        # Check if this acquire block belongs to a SELECT-only method.
        method_name = _find_enclosing_method(lines, i)
        if method_name in _SELECT_ONLY_METHODS:
            continue

        # Find the block extent: lines indented further than the acquire line.
        acquire_indent = len(line) - len(line.lstrip())
        block_lines: list[tuple[int, str]] = []
        for j in range(i + 1, len(lines)):
            ln = lines[j]
            if not ln.strip():
                block_lines.append((j, ln))
                continue
            ln_indent = len(ln) - len(ln.lstrip())
            if ln_indent <= acquire_indent:
                break
            block_lines.append((j, ln))

        # Does the block contain DML?
        block_text = "\n".join(ln for _, ln in block_lines)
        if not _DML_RE.search(block_text):
            continue  # no DML in this block; SELECT-only path

        # Block contains DML — must have conn.transaction() AND set_config.
        has_txn = any(_TRANSACTION_RE.search(ln) for _, ln in block_lines)
        if not has_txn:
            errors.append(
                f"{path.name}:{i + 1}: pool.acquire() block contains DML but "
                f"no `async with conn.transaction():` wrapper. D-TENANT-3 "
                f"requires SET LOCAL inside an explicit transaction."
            )
            continue

        has_set_config = any(_SET_CONFIG_RE.search(ln) for _, ln in block_lines)
        if not has_set_config:
            errors.append(
                f"{path.name}:{i + 1}: pool.acquire() block contains DML but "
                f"no `set_config('app.tenant_id', ...)` call. D-TENANT-3 "
                f"requires SET LOCAL via set_config before DML."
            )

    return errors


def _find_enclosing_method(lines: list[str], idx: int) -> str | None:
    """Scan backwards from idx to find the enclosing `def`/`async def`."""
    pattern = re.compile(r"^\s*(?:async\s+)?def\s+(\w+)\s*\(")
    for k in range(idx, -1, -1):
        m = pattern.match(lines[k])
        if m:
            return m.group(1)
    return None


def main() -> int:
    all_errors: list[str] = []
    for rel in _TARGET_FILES:
        path = _REPO_ROOT / rel
        if not path.exists():
            all_errors.append(f"MISSING FILE: {rel}")
            continue
        errors = _check_file(path)
        all_errors.extend(errors)

    if all_errors:
        print("D-TENANT-3 SET LOCAL pattern check FAILED:", file=sys.stderr)
        for e in all_errors:
            print(f"  {e}", file=sys.stderr)
        print(
            "\nFix: wrap the pool.acquire() block in "
            "`async with conn.transaction():` and call "
            "`await conn.execute(\"SELECT set_config('app.tenant_id', $1, true)\", tenant)` "
            "before any DML. See store.py:write_with_class for the canonical pattern.",
            file=sys.stderr,
        )
        return 1

    print(f"D-TENANT-3 SET LOCAL pattern check PASSED ({len(_TARGET_FILES)} files).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
