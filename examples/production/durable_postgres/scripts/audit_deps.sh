#!/usr/bin/env bash
# Pre-deploy dependency audit + multi-line SQL check (spec §6).
# Run before `docker compose build`.
#
# F-M-05: --strict exits non-zero on any advisory, including unfixable. To
# override a specific CVE that you've evaluated as not-applicable, append
# --ignore-vuln GHSA-XXXX-YYYY-ZZZZ to the pip-audit invocation below, AND
# add an inline comment naming the CVE and the rationale.
#
# A8-L-06: ALWAYS declare IGNORE_VULNS as an empty array — `set -u` plus an
# undeclared array reference (`"${IGNORE_VULNS[@]}"`) raises "unbound variable"
# on bash < 4.4. Adding ignores: edit the array between the two markers below.
#
# Example: IGNORE_VULNS=(--ignore-vuln GHSA-XXXX-YYYY-ZZZZ) # not exploitable

set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"

# BEGIN ignore-vulns
IGNORE_VULNS=()
# END ignore-vulns

echo "==> pip-audit (CVE check on hashed lockfile)"
# Safe array expansion: ${arr[@]+"${arr[@]}"} avoids unbound-var error even
# under `set -u` when the array is empty (pre-bash-4.4 portability).
pip-audit --require-hashes -r "$DIR/requirements.txt" --strict ${IGNORE_VULNS[@]+"${IGNORE_VULNS[@]}"}

echo "==> bandit B608 (SQL-injection patterns including concat + multi-line)"
# F-C-02: scripts/ and tests/ are NOT excluded — both contain SQL that
# warrants scanning. Bandit's B608 covers multi-line + concat where the
# grep gate cannot.
bandit -t B608 -r "$DIR"

echo "==> single-line f-string SQL grep"
bash "$DIR/scripts/check_no_fstring_sql.sh"

echo "OK: all dependency + SQL audits passed"
