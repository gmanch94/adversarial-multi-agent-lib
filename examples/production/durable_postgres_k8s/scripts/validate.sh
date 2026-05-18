#!/usr/bin/env bash
# Renders each overlay via kustomize, asserts exit 0. Optionally pipes to
# kubeconform if installed for schema validation.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KUSTOMIZE="${KUSTOMIZE:-kustomize}"

if ! command -v "$KUSTOMIZE" >/dev/null 2>&1; then
  echo "kustomize binary not found. Install: https://kustomize.io/" >&2
  exit 1
fi

for overlay in dev staging prod; do
  echo "Rendering overlays/${overlay}..."
  if "$KUSTOMIZE" build "${ROOT}/overlays/${overlay}" >/dev/null; then
    echo "  ok"
  else
    echo "  FAIL"
    exit 1
  fi
done

if command -v kubeconform >/dev/null 2>&1; then
  for overlay in dev staging prod; do
    echo "kubeconform overlays/${overlay}..."
    "$KUSTOMIZE" build "${ROOT}/overlays/${overlay}" \
      | kubeconform -strict -ignore-missing-schemas -summary
  done
fi

echo "All overlays render and validate."
