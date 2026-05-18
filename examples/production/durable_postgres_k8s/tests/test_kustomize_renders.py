"""Render tests for k8s overlays.

Skipped automatically when the `kustomize` binary is not on PATH (e.g. CI minutes
budget; root `testpaths = ["tests"]` already excludes this directory from the
library test run). Run explicitly via:

    pytest examples/production/durable_postgres_k8s/tests/
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

KUSTOMIZE = shutil.which("kustomize")
pytestmark = pytest.mark.skipif(
    KUSTOMIZE is None,
    reason="kustomize binary not installed",
)

ROOT = Path(__file__).resolve().parent.parent
OVERLAYS = ["dev", "staging", "prod"]

# D-K8S-3 hardening keys that must appear in every overlay render.
HARDENING_KEYS = [
    "runAsNonRoot: true",
    "readOnlyRootFilesystem: true",
    "allowPrivilegeEscalation: false",
    "seccompProfile",
    "RuntimeDefault",
    "drop:",
    "- ALL",
]


def _render(overlay: str, *, extra_dir: str | None = None) -> str:
    assert KUSTOMIZE is not None
    target = extra_dir or str(ROOT / "overlays" / overlay)
    result = subprocess.run(
        [KUSTOMIZE, "build", target],
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"kustomize build {target} failed:\nstdout={result.stdout}\nstderr={result.stderr}"
    )
    return result.stdout


@pytest.mark.parametrize("overlay", OVERLAYS)
def test_overlay_renders_clean(overlay: str) -> None:
    out = _render(overlay)
    assert out.strip(), f"{overlay} produced empty render"


@pytest.mark.parametrize("overlay", OVERLAYS)
def test_overlay_has_hardening_keys(overlay: str) -> None:
    out = _render(overlay)
    missing = [k for k in HARDENING_KEYS if k not in out]
    assert not missing, f"{overlay} missing hardening keys: {missing}"


@pytest.mark.parametrize("overlay", OVERLAYS)
def test_overlay_resource_limits_present(overlay: str) -> None:
    out = _render(overlay)
    assert "resources:" in out, f"{overlay} missing resources block"
    assert "requests:" in out and "limits:" in out, (
        f"{overlay} missing requests or limits"
    )


@pytest.mark.parametrize("overlay", OVERLAYS)
def test_overlay_automount_disabled(overlay: str) -> None:
    out = _render(overlay)
    assert "automountServiceAccountToken: false" in out, (
        f"{overlay} missing automountServiceAccountToken: false"
    )


def test_dev_has_no_default_deny() -> None:
    out = _render("dev")
    assert "name: default-deny" not in out, "dev should drop default-deny NetworkPolicy"


@pytest.mark.parametrize("overlay", ["staging", "prod"])
def test_staging_prod_enforces_default_deny(overlay: str) -> None:
    out = _render(overlay)
    assert "name: default-deny" in out, (
        f"{overlay} must keep default-deny NetworkPolicy"
    )


def test_prod_refuses_plain_secret() -> None:
    out = _render("prod")
    # The base plain Secret is $patch:delete-d; prod render must not contain
    # an `kind: Secret` whose metadata.name is durable-daemon-secrets.
    lines = out.splitlines()
    in_secret = False
    saw_plain = False
    for i, line in enumerate(lines):
        if line.strip() == "kind: Secret":
            in_secret = True
            continue
        if in_secret and line.startswith("  name: durable-daemon-secrets"):
            saw_plain = True
            break
        if in_secret and line.startswith("---"):
            in_secret = False
    assert not saw_plain, "prod overlay leaked a plain Secret named durable-daemon-secrets"


def test_prod_has_hpa() -> None:
    out = _render("prod")
    assert "kind: HorizontalPodAutoscaler" in out
    assert "durable_lock_pool_saturation" in out


def test_prod_has_sealed_secret_template() -> None:
    out = _render("prod")
    assert "kind: SealedSecret" in out
    assert "bitnami.com/v1alpha1" in out


def test_otel_component_renders_when_included(tmp_path: Path) -> None:
    """Compose a temporary overlay that includes components/otel."""
    overlay_dir = tmp_path / "with-otel"
    overlay_dir.mkdir()
    kustomization = overlay_dir / "kustomization.yaml"
    kustomization.write_text(
        f"""apiVersion: kustomize.config.k8s.io/v1beta1
kind: Kustomization
namespace: adv-multi-agent
resources:
  - {(ROOT / 'overlays' / 'prod').as_posix()}
components:
  - {(ROOT / 'components' / 'otel').as_posix()}
""",
        encoding="utf-8",
    )
    out = _render("with-otel", extra_dir=str(overlay_dir))
    for needle in (
        "name: otel-collector",
        "name: jaeger",
        "name: prometheus",
        "name: grafana",
    ):
        assert needle in out, f"otel component render missing {needle}"


@pytest.mark.parametrize("overlay", OVERLAYS)
def test_overlay_probe_split(overlay: str) -> None:
    """D-K8S-8: daemon Deployment exposes 3 distinct probe endpoints."""
    out = _render(overlay)
    assert "path: /health" in out, f"{overlay} missing /health startup probe"
    assert "path: /ready" in out, f"{overlay} missing /ready readiness probe"
    assert "path: /live" in out, f"{overlay} missing /live liveness probe"
