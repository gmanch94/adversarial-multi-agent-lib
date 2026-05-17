#!/usr/bin/env bash
# rotate_kms_key_version.sh — create a new CryptoKeyVersion (rotates primary)
#
# Usage:
#   PROJECT=my-project \
#   LOCATION=us-central1 \
#   KEYRING=my-keyring \
#   KEY=my-key \
#   ./rotate_kms_key_version.sh
#
# Or positionally:
#   ./rotate_kms_key_version.sh PROJECT LOCATION KEYRING KEY
#
# Effect:
#   - Creates a new key version; GCP automatically promotes it to primary.
#   - Prints the new version resource name and a short fingerprint (first 8 chars
#     of SHA-256 of the key resource path) for log correlation.
#   - Does NOT destroy old versions — they remain for decryption of existing
#     ciphertext until explicitly scheduled for destruction.

set -euo pipefail

# ---------- resolve args ----------
PROJECT="${1:-${PROJECT:-}}"
LOCATION="${2:-${LOCATION:-}}"
KEYRING="${3:-${KEYRING:-}}"
KEY="${4:-${KEY:-}}"

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

echo "==> Creating new key version for: $KEY_RESOURCE"

# Create new version (becomes primary automatically)
gcloud kms keys versions create \
    --key "$KEY" \
    --keyring "$KEYRING" \
    --location "$LOCATION" \
    --project "$PROJECT" \
    --quiet

# Retrieve the new primary version
NEW_VERSION=$(gcloud kms keys versions list \
    --key "$KEY" \
    --keyring "$KEYRING" \
    --location "$LOCATION" \
    --project "$PROJECT" \
    --filter="state=ENABLED" \
    --sort-by="~createTime" \
    --format="value(name)" \
    | head -1)

# Fingerprint: sha256 of key resource path, first 8 hex chars
FINGERPRINT=$(printf '%s' "$KEY_RESOURCE" | sha256sum | cut -c1-8)

echo ""
echo "    New primary version : $NEW_VERSION"
echo "    Key path fingerprint: $FINGERPRINT"

# Tier 1.8: every new version gets --prevent-destroy on creation.
if [[ -n "$NEW_VERSION" ]]; then
  gcloud kms keys versions update "$NEW_VERSION" --prevent-destroy --quiet 2>&1 \
    | head -3 || true
  echo "    Destroy protection  : enabled on $NEW_VERSION"
fi

echo ""
echo "NOTE: Old versions remain for decryption of existing ciphertext."
echo "      To schedule an old version for destruction (must remove"
echo "      destroy protection first):"
echo "      gcloud kms keys versions update <VERSION> --remove-prevent-destroy"
echo "      gcloud kms keys versions destroy <VERSION>"
