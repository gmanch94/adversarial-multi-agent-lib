#!/usr/bin/env bash
# Pre-commit SQL-injection grep gate (spec §4.1.11).
# Fails if any Python file in this dir embeds SQL keywords inside an f-string.
# Stacked with bandit B608 in audit_deps.sh for multi-line cases.
#
# F-C-02: scripts/ is INCLUDED in the scan (was excluded in plan v1).
# scripts/reencrypt_all.py contains live SQL; any future f-string regression
# there is exactly what this gate exists to catch. tests/ is also INCLUDED
# now — there is no legitimate reason for tests to embed f-string SQL since
# parameterized queries are equally testable.

set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Use ripgrep if available; fall back to grep.
# Match f-string with SELECT/INSERT/UPDATE/DELETE at start of content (actual SQL, not keywords in strings).
# Exclude test_grep_gate.py (this test file intentionally contains bad patterns for validation).
if command -v rg >/dev/null 2>&1; then
    if rg -n --type py \
        'f"(SELECT|INSERT|UPDATE|DELETE)' "$DIR" \
        --glob '!test_grep_gate.py' 2>/dev/null; then
        echo "ERROR: f-string SQL detected. Use asyncpg parameterized queries." >&2
        exit 1
    fi
else
    if grep -rn --include='*.py' \
        'f"\(SELECT\|INSERT\|UPDATE\|DELETE\)' "$DIR" 2>/dev/null \
        | grep -v 'test_grep_gate.py'; then
        echo "ERROR: f-string SQL detected. Use asyncpg parameterized queries." >&2
        exit 1
    fi
fi

echo "OK: no f-string SQL detected in $DIR"
