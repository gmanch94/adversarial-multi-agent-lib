#!/usr/bin/env bash
# provision_cmk.sh — idempotent CMK + alias + key policy + CloudTrail Data Events.
#
# Usage:
#   AWS_REGION=us-east-1 AWS_PROFILE=admin ./scripts/provision_cmk.sh
#
# Requires:
#   - aws CLI authenticated as an admin principal with kms:CreateKey,
#     kms:CreateAlias, cloudtrail:PutEventSelectors permissions.
#   - $AWS_REGION set.
#   - Optional: $DAEMON_ROLE_ARN (the durable-daemon-role); when set, the
#     key policy grants Encrypt/Decrypt/GenerateDataKey to that role.
#   - Optional: $ADMIN_ROLE_ARN (the durable-admin-role); when set, granted
#     ScheduleKeyDeletion / DescribeKey.
#
# Idempotent: re-running is safe; existing alias is reused.

set -euo pipefail

ALIAS="${ALIAS:-alias/durable-payload-dek-wrapper}"
REGION="${AWS_REGION:?AWS_REGION must be set}"
ACCOUNT="$(aws sts get-caller-identity --query Account --output text)"

# Step 1: discover or create CMK.
EXISTING_KEY_ID="$(aws kms describe-key --key-id "$ALIAS" --region "$REGION" \
  --query 'KeyMetadata.KeyId' --output text 2>/dev/null || true)"

if [[ -n "$EXISTING_KEY_ID" && "$EXISTING_KEY_ID" != "None" ]]; then
  echo "CMK already exists for alias=$ALIAS; KeyId=$EXISTING_KEY_ID"
  KEY_ID="$EXISTING_KEY_ID"
else
  echo "Creating CMK..."
  KEY_ID="$(aws kms create-key \
    --region "$REGION" \
    --description "Durable workflow payload DEK wrapper" \
    --key-usage ENCRYPT_DECRYPT \
    --key-spec SYMMETRIC_DEFAULT \
    --query 'KeyMetadata.KeyId' \
    --output text)"
  echo "Created KeyId=$KEY_ID"

  aws kms create-alias \
    --region "$REGION" \
    --alias-name "$ALIAS" \
    --target-key-id "$KEY_ID"
  echo "Alias $ALIAS -> $KEY_ID"

  aws kms enable-key-rotation --region "$REGION" --key-id "$KEY_ID"
  echo "Auto-rotation enabled."
fi

# Step 2: write key policy (separation of duties).
POLICY_FILE="$(mktemp)"
cat > "$POLICY_FILE" <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "RootAccountAccess",
      "Effect": "Allow",
      "Principal": {"AWS": "arn:aws:iam::${ACCOUNT}:root"},
      "Action": "kms:*",
      "Resource": "*"
    }$( [[ -n "${DAEMON_ROLE_ARN:-}" ]] && cat <<DAEMON
    ,
    {
      "Sid": "DurableDaemonKmsEnvelope",
      "Effect": "Allow",
      "Principal": {"AWS": "${DAEMON_ROLE_ARN}"},
      "Action": ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"],
      "Resource": "*"
    }
DAEMON
)$( [[ -n "${ADMIN_ROLE_ARN:-}" ]] && cat <<ADMIN
    ,
    {
      "Sid": "DurableAdminKmsRotation",
      "Effect": "Allow",
      "Principal": {"AWS": "${ADMIN_ROLE_ARN}"},
      "Action": ["kms:ScheduleKeyDeletion", "kms:CancelKeyDeletion", "kms:UpdateAlias", "kms:DescribeKey", "kms:EnableKeyRotation"],
      "Resource": "*"
    }
ADMIN
)
  ]
}
EOF

aws kms put-key-policy \
  --region "$REGION" \
  --key-id "$KEY_ID" \
  --policy-name default \
  --policy "file://$POLICY_FILE"
rm -f "$POLICY_FILE"
echo "Key policy applied."

# Step 3: CloudTrail Data Events on KMS Decrypt — operator-visible decision.
# Costs $0.10 / 100k events; opt-in by setting CLOUDTRAIL_NAME.
if [[ -n "${CLOUDTRAIL_NAME:-}" ]]; then
  aws cloudtrail put-event-selectors \
    --region "$REGION" \
    --trail-name "$CLOUDTRAIL_NAME" \
    --event-selectors "[{
      \"ReadWriteType\": \"All\",
      \"IncludeManagementEvents\": true,
      \"DataResources\": [{
        \"Type\": \"AWS::KMS::Key\",
        \"Values\": [\"arn:aws:kms:${REGION}:${ACCOUNT}:key/${KEY_ID}\"]
      }]
    }]"
  echo "CloudTrail Data Events enabled on trail=$CLOUDTRAIL_NAME"
else
  echo "Skipping CloudTrail Data Events (set CLOUDTRAIL_NAME to enable; costs apply)."
fi

echo
echo "Done. CMK ARN: arn:aws:kms:${REGION}:${ACCOUNT}:key/${KEY_ID}"
echo "Set AWS_KMS_CMK_ALIAS=${ALIAS} in your daemon .env."
