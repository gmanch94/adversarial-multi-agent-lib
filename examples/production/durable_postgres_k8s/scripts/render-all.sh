#!/usr/bin/env bash
# Renders each overlay to /tmp for visual diff review.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
OUT="${OUT:-/tmp}"
KUSTOMIZE="${KUSTOMIZE:-kustomize}"

for overlay in dev staging prod; do
  out="${OUT}/k8s-render-${overlay}.yaml"
  "$KUSTOMIZE" build "${ROOT}/overlays/${overlay}" > "$out"
  echo "wrote ${out}"
done
