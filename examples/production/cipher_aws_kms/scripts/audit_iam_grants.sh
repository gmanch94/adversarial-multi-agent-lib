#!/usr/bin/env bash
# audit_iam_grants.sh — list every principal with kms:Decrypt on the CMK.
#
# Pre-deploy gate. Compare output against expected daemon + admin roles only.
# Any unexpected principal = stop deploy, investigate.
#
# Usage:
#   AWS_REGION=us-east-1 AWS_PROFILE=auditor ./scripts/audit_iam_grants.sh

set -euo pipefail

ALIAS="${ALIAS:-alias/durable-payload-dek-wrapper}"
REGION="${AWS_REGION:?AWS_REGION must be set}"

KEY_ID="$(aws kms describe-key --key-id "$ALIAS" --region "$REGION" \
  --query 'KeyMetadata.KeyId' --output text)"

echo "Key policy principals (statement Sid + Principal):"
aws kms get-key-policy --region "$REGION" --key-id "$KEY_ID" \
  --policy-name default \
  --query 'Policy' --output text | python3 -c '
import json, sys
pol = json.loads(sys.stdin.read())
for st in pol.get("Statement", []):
    sid = st.get("Sid", "<no-sid>")
    p = st.get("Principal", {})
    actions = st.get("Action", [])
    if isinstance(actions, str):
        actions = [actions]
    if any(a in ("kms:Decrypt", "kms:*") or a.startswith("kms:") for a in actions):
        print(f"  Sid={sid}  Principal={p}  Action={actions}")
'

echo
echo "KMS grants on this key (kms:Decrypt only):"
aws kms list-grants --region "$REGION" --key-id "$KEY_ID" \
  --query 'Grants[?contains(Operations, `Decrypt`)].[GranteePrincipal,GrantId,Name]' \
  --output table || echo "  (no grants)"

echo
echo "Done. Compare against expected daemon + admin role ARNs."
