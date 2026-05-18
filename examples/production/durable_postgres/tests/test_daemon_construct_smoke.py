"""Tier 3.6 regression gate — verify SchedulerDaemon construction kwargs.

Pre-existing latent bug surfaced by Tier 2.1c-sibling-2 audit: all 4
sibling daemons were calling `SchedulerDaemon(checkpoint_store=store)`
but library `__init__` takes `scheduler: PollingScheduler`. Would
TypeError on first daemon construct.

This test does NOT run the daemon (requires Postgres + API keys). It
imports each daemon module and inspects via the AST/inspect that the
SchedulerDaemon call uses the correct kwarg.
"""
from __future__ import annotations

import ast
import inspect
from pathlib import Path

from adv_multi_agent.core.durable.scheduler import SchedulerDaemon


def _scheduler_daemon_accepted_kwargs() -> set[str]:
    sig = inspect.signature(SchedulerDaemon.__init__)
    return set(sig.parameters) - {"self"}


def _scheduler_daemon_required_kwargs() -> set[str]:
    """Params with no default and not *args/**kwargs."""
    sig = inspect.signature(SchedulerDaemon.__init__)
    required = set()
    for name, p in sig.parameters.items():
        if name == "self":
            continue
        if p.kind in (p.VAR_POSITIONAL, p.VAR_KEYWORD):
            continue
        if p.default is inspect.Parameter.empty:
            required.add(name)
    return required


def _extract_kwargs_at_call(source: str, call_name: str) -> set[str]:
    """Find first call to `call_name` in source; return its kwarg names.

    Tier 2.1d / LOW-2 audit harden: matches both `SchedulerDaemon(...)`
    (ast.Name) AND `scheduler.SchedulerDaemon(...)` (ast.Attribute). A
    future refactor that switches to attribute-style imports must not
    silently bypass the gate.
    """
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == call_name:
            return {kw.arg for kw in node.keywords if kw.arg is not None}
        if isinstance(func, ast.Attribute) and func.attr == call_name:
            return {kw.arg for kw in node.keywords if kw.arg is not None}
    raise AssertionError(f"no call to {call_name} found")


def _check(daemon_path: str) -> None:
    src = Path(daemon_path).read_text(encoding="utf-8")
    kwargs = _extract_kwargs_at_call(src, "SchedulerDaemon")
    accepted = _scheduler_daemon_accepted_kwargs()
    required = _scheduler_daemon_required_kwargs()
    unknown = kwargs - accepted
    missing = required - kwargs
    assert not unknown, (
        f"{daemon_path} passes kwargs not accepted by SchedulerDaemon: "
        f"{sorted(unknown)!r}; accepted: {sorted(accepted)!r}"
    )
    # Tier 2.1d / T2 audit harden: catch missing required kwargs too.
    # Pre-fix daemon was passing `checkpoint_store=` (unknown) AND missing
    # `scheduler=` (required). The unknown-check caught half the bug.
    assert not missing, (
        f"{daemon_path} missing required SchedulerDaemon kwargs: "
        f"{sorted(missing)!r}"
    )


def test_durable_postgres_daemon_kwargs_match() -> None:
    _check("examples/production/durable_postgres/daemon.py")


def test_cipher_gcp_kms_daemon_kwargs_match() -> None:
    _check("examples/production/cipher_gcp_kms/daemon.py")


def test_cipher_aws_kms_daemon_kwargs_match() -> None:
    _check("examples/production/cipher_aws_kms/daemon.py")


def test_durable_postgres_otel_daemon_kwargs_match() -> None:
    _check("examples/production/durable_postgres_otel/daemon.py")
