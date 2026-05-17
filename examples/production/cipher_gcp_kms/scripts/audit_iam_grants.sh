#!/usr/bin/env bash
# audit_iam_grants.sh — verify IAM grants on a Cloud KMS key
#
# Usage:
#   PROJECT=my-project \
#   LOCATION=us-central1 \
#   KEYRING=my-keyring \
#   KEY=my-key \
#   [EXPECTED_BINDINGS_COUNT=2] \
#   ./audit_iam_grants.sh
#
# Or positionally:
#   ./audit_iam_grants.sh PROJECT LOCATION KEYRING KEY [EXPECTED_BINDINGS_COUNT]
#
# Output:
#   Table of every principal bound to:
#     - roles/cloudkms.cryptoKeyEncrypterDecrypter
#     - roles/cloudkms.admin
#   Exit 0 if count matches EXPECTED_BINDINGS_COUNT (default 2).
#   Exit 1 if count differs — signals unexpected grants.

set -euo pipefail

# ---------- resolve args ----------
PROJECT="${1:-${PROJECT:-}}"
LOCATION="${2:-${LOCATION:-}}"
KEYRING="${3:-${KEYRING:-}}"
KEY="${4:-${KEY:-}}"
EXPECTED_BINDINGS_COUNT="${5:-${EXPECTED_BINDINGS_COUNT:-2}}"

missing=()
[[ -z "$PROJECT"  ]] && missing+=("PROJECT")
[[ -z "$LOCATION" ]] && missing+=("LOCATION")
[[ -z "$KEYRING"  ]] && missing+=("KEYRING")
[[ -z "$KEY"      ]] && missing+=("KEY")

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "ERROR: missing required variables: ${missing[*]}" >&2
  exit 1
fi

# Fail-loud if no active gcloud account
active_account=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1)
if [[ -z "$active_account" ]]; then
  echo "ERROR: no active gcloud account. Run: gcloud auth login" >&2
  exit 1
fi

KEY_RESOURCE="projects/$PROJECT/locations/$LOCATION/keyRings/$KEYRING/cryptoKeys/$KEY"

echo "==> IAM policy audit for: $KEY_RESOURCE"
echo ""

# Fetch full policy as JSON
POLICY_JSON=$(gcloud kms keys get-iam-policy "$KEY" \
    --keyring "$KEYRING" \
    --location "$LOCATION" \
    --project "$PROJECT" \
    --format=json 2>/dev/null)

# Export JSON before the first heredoc so both python sub-shells can read it.
# A9-H-01: original code ran the first heredoc before the export, so
# _POLICY_JSON was always empty → table always printed "(no sensitive KMS
# bindings found)". Moving the export here fixes the operator-visible table.
export _POLICY_JSON="$POLICY_JSON"

# Extract relevant bindings using python (available in gcloud SDK environments)
AUDIT_OUTPUT=$(python3 - <<'PYEOF'
import json, sys, os

policy = json.loads(os.environ.get("_POLICY_JSON", "{}"))

SENSITIVE_ROLES = {
    "roles/cloudkms.cryptoKeyEncrypterDecrypter",
    "roles/cloudkms.admin",
    # Include encrypter-only and decrypter-only for completeness
    "roles/cloudkms.cryptoKeyEncrypter",
    "roles/cloudkms.cryptoKeyDecrypter",
}

bindings = policy.get("bindings", [])
rows = []
for b in bindings:
    role = b.get("role", "")
    if role in SENSITIVE_ROLES:
        for member in b.get("members", []):
            rows.append((role, member))

if not rows:
    print("  (no sensitive KMS bindings found)")
else:
    col1 = max(len(r[0]) for r in rows)
    col2 = max(len(r[1]) for r in rows)
    header = f"  {'ROLE':<{col1}}  {'PRINCIPAL':<{col2}}"
    sep    = f"  {'-'*col1}  {'-'*col2}"
    print(header)
    print(sep)
    for role, member in rows:
        print(f"  {role:<{col1}}  {member:<{col2}}")

print(f"\n  Total sensitive bindings: {len(rows)}")
sys.exit(0)
PYEOF
)

echo "$AUDIT_OUTPUT"

# Re-run python to get count for gate check
BINDING_COUNT=$(python3 - <<'PYEOF'
import json, os

policy = json.loads(os.environ.get("_POLICY_JSON", "{}"))
SENSITIVE_ROLES = {
    "roles/cloudkms.cryptoKeyEncrypterDecrypter",
    "roles/cloudkms.admin",
    "roles/cloudkms.cryptoKeyEncrypter",
    "roles/cloudkms.cryptoKeyDecrypter",
}
count = sum(
    len(b.get("members", []))
    for b in policy.get("bindings", [])
    if b.get("role", "") in SENSITIVE_ROLES
)
print(count)
PYEOF
)

echo ""
echo "  Expected bindings : $EXPECTED_BINDINGS_COUNT"
echo "  Actual bindings   : $BINDING_COUNT"

if [[ "$BINDING_COUNT" -ne "$EXPECTED_BINDINGS_COUNT" ]]; then
  echo ""
  echo "ERROR: binding count mismatch ($BINDING_COUNT != $EXPECTED_BINDINGS_COUNT)." >&2
  echo "       Review the table above and remove unexpected principals before deploy." >&2
  exit 1
fi

echo ""
echo "==> IAM audit PASSED. Binding count matches expected ($EXPECTED_BINDINGS_COUNT)."
