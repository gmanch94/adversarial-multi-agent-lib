#!/usr/bin/env bash
# rotate_cmk_now.sh — force manual key-material rotation (vs annual auto).
#
# AWS handles the rotation transparently: GenerateDataKey starts wrapping
# with new key material on the next call; existing wrapped DEKs continue
# to decrypt against historical material until the deletion window elapses.
# No daemon restart needed.
#
# Usage:
#   AWS_REGION=us-east-1 AWS_PROFILE=admin ./scripts/rotate_cmk_now.sh

set -euo pipefail

ALIAS="${ALIAS:-alias/durable-payload-dek-wrapper}"
REGION="${AWS_REGION:?AWS_REGION must be set}"

KEY_ID="$(aws kms describe-key --key-id "$ALIAS" --region "$REGION" \
  --query 'KeyMetadata.KeyId' --output text)"

echo "Rotating key material for KeyId=$KEY_ID (alias=$ALIAS)..."
aws kms rotate-key-on-demand --region "$REGION" --key-id "$KEY_ID"
echo "Rotation initiated. No daemon restart required."
echo
echo "Verify in CloudTrail: look for KMS.RotateKeyOnDemand event."
echo "New fingerprint of wrapped DEKs will appear in healthcheck /health."
