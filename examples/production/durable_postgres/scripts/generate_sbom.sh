#!/usr/bin/env bash
# Generate CycloneDX SBOM from the locked requirements (spec §6.2.8).
# Run before deploy; commit sbom.cdx.json alongside requirements.txt changes.

set -euo pipefail

DIR="$(cd "$(dirname "$0")/.." && pwd)"

cyclonedx-py requirements \
    -i "$DIR/requirements.txt" \
    -o "$DIR/sbom.cdx.json"

echo "OK: SBOM written to $DIR/sbom.cdx.json"
