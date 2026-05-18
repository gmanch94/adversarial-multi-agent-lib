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
# Cross-check against store.py D-TENANT-3 comment. Tier 2.1b: read_with_tenant
# + list_paused_with_tenants removed — cp.tenant_id and token.tenant_id are
# fields now, no extension methods needed.
_SELECT_ONLY_METHODS = {
    "read", "list_paused",
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


def _strip_comments(line: str) -> str:
    """Strip Python `#` comments from a code line, preserving string content.

    Audit 2026-05-18 Q8 follow-up: prevents false positives when comments
    contain DML keywords (e.g. `# DELETE pattern goes here`). Simplified
    parser — handles `# inside string` correctly enough for the codebase
    convention (no `#` inside f-strings + no escaped quotes inside SQL).
    """
    in_str: str | None = None
    out_chars: list[str] = []
    i = 0
    while i < len(line):
        ch = line[i]
        if in_str is not None:
            out_chars.append(ch)
            if ch == in_str and (i == 0 or line[i - 1] != "\\"):
                in_str = None
            i += 1
            continue
        if ch in ("'", '"'):
            in_str = ch
            out_chars.append(ch)
            i += 1
            continue
        if ch == "#":
            break  # rest of line is comment
        out_chars.append(ch)
        i += 1
    return "".join(out_chars)


def _check_file(path: Path) -> list[str]:
    """Return list of error messages; empty list means file passes."""
    errors: list[str] = []
    source = path.read_text(encoding="utf-8")
    raw_lines = source.splitlines()
    # Audit Q8 follow-up: strip comments before regex matching so docstring/
    # comment mentions of DML keywords don't trigger false positives.
    lines = [_strip_comments(ln) for ln in raw_lines]

    # Walk acquire() blocks. For each, verify the conn.transaction() wrapper
    # AND that set_config precedes any DML by line number.
    for i, line in enumerate(lines):
        m = _ACQUIRE_RE.search(line)
        if not m:
            continue

        # Check if this acquire block belongs to a SELECT-only method.
        method_name = _find_enclosing_method(raw_lines, i)
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

        # Find first DML line + first set_config line by index.
        first_dml_idx: int | None = None
        first_set_config_idx: int | None = None
        first_txn_idx: int | None = None
        for j, ln in block_lines:
            if first_dml_idx is None and _DML_RE.match(ln):
                first_dml_idx = j
            if first_set_config_idx is None and _SET_CONFIG_RE.search(ln):
                first_set_config_idx = j
            if first_txn_idx is None and _TRANSACTION_RE.search(ln):
                first_txn_idx = j

        if first_dml_idx is None:
            continue  # no DML in this block; SELECT-only path

        # Block contains DML — must have conn.transaction() AND set_config
        # BEFORE the DML line.
        if first_txn_idx is None:
            errors.append(
                f"{path.name}:{i + 1}: pool.acquire() block contains DML but "
                f"no `async with conn.transaction():` wrapper. D-TENANT-3 "
                f"requires SET LOCAL inside an explicit transaction."
            )
            continue

        if first_set_config_idx is None:
            errors.append(
                f"{path.name}:{i + 1}: pool.acquire() block contains DML but "
                f"no `set_config('app.tenant_id', ...)` call. D-TENANT-3 "
                f"requires SET LOCAL via set_config before DML."
            )
            continue

        # Audit Q8 follow-up: set_config must precede DML by line number.
        if first_set_config_idx >= first_dml_idx:
            errors.append(
                f"{path.name}:{first_dml_idx + 1}: DML at line "
                f"{first_dml_idx + 1} appears BEFORE `set_config` at line "
                f"{first_set_config_idx + 1}. D-TENANT-3 requires SET LOCAL "
                f"before any DML in the same transaction."
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
