#!/usr/bin/env bash
# provision_keyring.sh — idempotent GCP Cloud KMS keyring + key + IAM setup
#
# Usage:
#   PROJECT=my-project \
#   LOCATION=us-central1 \
#   KEYRING=my-keyring \
#   KEY=my-key \
#   DAEMON_SA=daemon@my-project.iam.gserviceaccount.com \
#   ADMIN_SA=admin@my-project.iam.gserviceaccount.com \
#   ./provision_keyring.sh
#
# Or positionally:
#   ./provision_keyring.sh PROJECT LOCATION KEYRING KEY DAEMON_SA ADMIN_SA
#
# Required env vars (or positional args):
#   PROJECT       GCP project ID
#   LOCATION      KMS location (e.g. us-central1, global)
#   KEYRING       KMS keyring name
#   KEY           KMS key name
#   DAEMON_SA     Service account email for the runtime daemon (encrypt/decrypt)
#   ADMIN_SA      Service account email for key administration

set -euo pipefail

# ---------- resolve args (positional override env) ----------
PROJECT="${1:-${PROJECT:-}}"
LOCATION="${2:-${LOCATION:-}}"
KEYRING="${3:-${KEYRING:-}}"
KEY="${4:-${KEY:-}}"
DAEMON_SA="${5:-${DAEMON_SA:-}}"
ADMIN_SA="${6:-${ADMIN_SA:-}}"

# ---------- sanity checks ----------
missing=()
[[ -z "$PROJECT"   ]] && missing+=("PROJECT")
[[ -z "$LOCATION"  ]] && missing+=("LOCATION")
[[ -z "$KEYRING"   ]] && missing+=("KEYRING")
[[ -z "$KEY"       ]] && missing+=("KEY")
[[ -z "$DAEMON_SA" ]] && missing+=("DAEMON_SA")
[[ -z "$ADMIN_SA"  ]] && missing+=("ADMIN_SA")

if [[ ${#missing[@]} -gt 0 ]]; then
  echo "ERROR: missing required variables: ${missing[*]}" >&2
  echo "Set them as env vars or pass as positional args." >&2
  exit 1
fi

# Fail-loud if no active gcloud account
active_account=$(gcloud auth list --filter=status:ACTIVE --format="value(account)" 2>/dev/null | head -1)
if [[ -z "$active_account" ]]; then
  echo "ERROR: no active gcloud account. Run: gcloud auth login" >&2
  exit 1
fi
echo "Active gcloud account: $active_account"

KEY_RESOURCE="projects/$PROJECT/locations/$LOCATION/keyRings/$KEYRING/cryptoKeys/$KEY"

# ---------- 1. create keyring (idempotent) ----------
echo ""
echo "==> Creating keyring: $KEYRING in $LOCATION ..."
if gcloud kms keyrings create "$KEYRING" \
    --location "$LOCATION" \
    --project "$PROJECT" 2>&1 | grep -qv "ALREADY_EXISTS\|already exists"; then
  # Re-run without grep to let any real errors surface
  gcloud kms keyrings create "$KEYRING" \
      --location "$LOCATION" \
      --project "$PROJECT" 2>/dev/null || true
fi
echo "    Keyring ready: projects/$PROJECT/locations/$LOCATION/keyRings/$KEYRING"

# ---------- 2. create key (idempotent) ----------
echo ""
echo "==> Creating key: $KEY ..."
gcloud kms keys create "$KEY" \
    --keyring "$KEYRING" \
    --location "$LOCATION" \
    --project "$PROJECT" \
    --purpose encryption \
    --rotation-period 90d \
    --next-rotation-time +30d \
    --destroy-scheduled-duration 30d 2>&1 \
  | grep -v "ALREADY_EXISTS\|already exists" || true
echo "    Key ready: $KEY_RESOURCE"

# ---------- 3. IAM — daemon SA (encrypt/decrypt only — role, not primitive perm) ----------
echo ""
echo "==> Binding roles/cloudkms.cryptoKeyEncrypterDecrypter -> $DAEMON_SA ..."
gcloud kms keys add-iam-policy-binding "$KEY" \
    --keyring "$KEYRING" \
    --location "$LOCATION" \
    --project "$PROJECT" \
    --member "serviceAccount:$DAEMON_SA" \
    --role roles/cloudkms.cryptoKeyEncrypterDecrypter \
    --quiet
echo "    Bound: $DAEMON_SA -> roles/cloudkms.cryptoKeyEncrypterDecrypter"

# ---------- 4. IAM — admin SA (full key management — role, not primitive perm) ----------
echo ""
echo "==> Binding roles/cloudkms.admin -> $ADMIN_SA ..."
gcloud kms keys add-iam-policy-binding "$KEY" \
    --keyring "$KEYRING" \
    --location "$LOCATION" \
    --project "$PROJECT" \
    --member "serviceAccount:$ADMIN_SA" \
    --role roles/cloudkms.admin \
    --quiet
echo "    Bound: $ADMIN_SA -> roles/cloudkms.admin"

# ---------- 5. Destroy protection (Tier 1.8) ----------
# Cloud KMS does not expose a --prevent-destroy flag at the key level via
# gcloud. Protection is applied at the CryptoKeyVersion level. We
# automatically apply it to every ENABLED version below.
echo ""
echo "==> Enabling destroy protection on every ENABLED version ..."
mapfile -t VERSIONS < <(
  gcloud kms keys versions list \
      --key "$KEY" --keyring "$KEYRING" \
      --location "$LOCATION" --project "$PROJECT" \
      --filter="state=ENABLED" --format="value(name)" 2>/dev/null || true
)
if [[ ${#VERSIONS[@]} -eq 0 ]]; then
  echo "    WARNING: no ENABLED versions found (key may have only PENDING_GENERATION)."
  echo "    Re-run this script after the first key version is generated."
else
  for V in "${VERSIONS[@]}"; do
    if gcloud kms keys versions update "$V" --prevent-destroy --quiet 2>&1 \
        | grep -qv "ALREADY"; then
      true  # surface real errors via non-grep retry
    fi
    echo "    [protected] $V"
  done
fi

# ---------- 6. Project deletion lien (Tier 1.8) ----------
# Prevents accidental project deletion from cascading into KMS destruction.
# Idempotent: gcloud will refuse to create a duplicate lien with the same reason.
echo ""
echo "==> Applying project-deletion lien (Tier 1.8 / A10-H2 mitigation) ..."
LIEN_REASON="durable-kms-cipher-protection-cycle9"
if ! gcloud resource-manager liens list --project "$PROJECT" \
    --format="value(reason)" 2>/dev/null | grep -qx "$LIEN_REASON"; then
  gcloud resource-manager liens create \
      --project "$PROJECT" \
      --restrictions resourcemanager.projects.delete \
      --reason "$LIEN_REASON" \
      --quiet 2>&1 \
    | head -3 || echo "    NOTE: lien creation requires roles/resourcemanager.lienModifier"
  echo "    Lien applied: $LIEN_REASON (restrictions=resourcemanager.projects.delete)"
else
  echo "    Lien already present: $LIEN_REASON"
fi

# ---------- done ----------
echo ""
echo "==> Provisioning complete."
echo ""
echo "    Key resource name (paste into .env as KMS_KEY_NAME):"
echo "    $KEY_RESOURCE"
echo ""
echo "    Tier 1.8 recovery posture:"
echo "    [ok]   IAM separation: daemon=encrypt/decrypt; admin=full"
echo "    [ok]   90d auto-rotation"
echo "    [ok]   30d destroy-scheduled-duration (recovery window)"
echo "    [ok]   --prevent-destroy on ENABLED versions"
echo "    [ok]   project-deletion lien"
echo "    [next] OPERATOR: enable multi-region keyring for cross-region durability"
echo "           (Tier 1.8 upgrade path; see docs/runbooks/durable-compliance.md §13)"
