"""EncryptedCheckpointStore — decorator that encrypts Checkpoint.last_request_json
at rest AND computes a full-Checkpoint integrity tag (SEAL:v1:) using a
caller-supplied Cipher.

Closes H-DUR-4 (PHI bleed-through via plaintext request JSON in checkpoint
files) and A10-H2 (insider tamper of workflow_version_hash / rounds_history /
status undetected — full-Checkpoint integrity tag added in Tier 1.9 Slice A).

Field-level encryption (last_request_json) + full-row integrity tag:
- Encryption is OPT-IN — callers handling PHI MUST wrap their CheckpointStore
  in EncryptedCheckpointStore + supply a Cipher.
- The integrity tag covers ALL Checkpoint fields except integrity_tag itself,
  computed on the post-encryption form so the tag binds to the bytes actually
  persisted. Reads verify the tag fail-closed via IntegrityViolation.
- Pre-1.9 rows (integrity_tag is None) emit LegacyPartialAEADWarning on read
  and reseal on the next write — operators should run reseal_all_checkpoints.py
  (Slice B) to upgrade in bulk.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import re
import warnings
from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime
from typing import Any

from .checkpoint import Checkpoint
from .protocols import Cipher, IntegrityViolation
from .token import ResumeToken


class UnknownTenantError(KeyError):
    """D-TENANT-7 (Tier 2.1c): raised when a `cipher_for_tenant` resolver
    cannot map a tenant_id to a Cipher.

    EncryptedCheckpointStore.seal/unseal/write/read fail closed when this
    is raised — no fallback decrypt path. Operator runbooks instruct: if
    this fires unexpectedly, the resolver / KMS / keyring is misconfigured.
    """


class LegacyPartialAEADWarning(UserWarning):
    """Emitted when EncryptedCheckpointStore reads a pre-1.9 checkpoint
    that has no integrity_tag (field-only AEAD, A10-H2 attack surface).
    Operator should run reseal_all_checkpoints.py to upgrade."""


def _canonical_checkpoint_bytes(cp: Checkpoint) -> bytes:
    """Canonical JSON of all Checkpoint fields EXCEPT integrity_tag.
    Deterministic across Python versions (sort_keys + compact separators)."""
    d = asdict(cp)
    d.pop("integrity_tag", None)
    return json.dumps(
        d, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")


def _compute_integrity_payload(cp: Checkpoint) -> str:
    """Build the SEAL:v1:<run_id>:<schema_version>:<hex_sha256> plaintext
    that gets encrypted via Cipher.encrypt to form the integrity tag."""
    h = hashlib.sha256(_canonical_checkpoint_bytes(cp)).hexdigest()
    return f"SEAL:v1:{cp.run_id}:{cp.schema_version}:{h}"


def _replace_integrity_tag(cp: Checkpoint, new_tag: str | None) -> Checkpoint:
    """Return a NEW Checkpoint with integrity_tag swapped, all other fields preserved."""
    return Checkpoint(
        run_id=cp.run_id,
        tenant_id=cp.tenant_id,
        schema_version=cp.schema_version,
        status=cp.status,
        round=cp.round,
        rounds_history=cp.rounds_history,
        last_request_json=cp.last_request_json,
        pause_reason=cp.pause_reason,
        pause_context=cp.pause_context,
        budget_used=cp.budget_used,
        pinned_executor_model=cp.pinned_executor_model,
        pinned_reviewer_model=cp.pinned_reviewer_model,
        created_at=cp.created_at,
        updated_at=cp.updated_at,
        wake_at=cp.wake_at,
        workflow_version_hash=cp.workflow_version_hash,
        integrity_tag=new_tag,
    )


def _verify_integrity_payload(payload: str, cp: Checkpoint) -> None:
    """Parse SEAL:v1:<run_id>:<schema_version>:<hex_sha256> and verify
    each component against the freshly-read checkpoint. Raises
    IntegrityViolation on any mismatch (fail-closed)."""
    parts = payload.split(":", 4)
    if len(parts) != 5 or parts[0] != "SEAL" or parts[1] != "v1":
        raise IntegrityViolation(
            run_id=cp.run_id,
            expected_hash="<bad-payload>",
            observed_hash=payload[:32],
        )
    _, _, payload_run_id, payload_schema, payload_hash = parts
    if payload_run_id != cp.run_id:
        raise IntegrityViolation(
            run_id=cp.run_id,
            expected_hash=f"run_id={payload_run_id}",
            observed_hash=f"run_id={cp.run_id}",
        )
    if str(payload_schema) != str(cp.schema_version):
        raise IntegrityViolation(
            run_id=cp.run_id,
            expected_hash=f"schema={payload_schema}",
            observed_hash=f"schema={cp.schema_version}",
        )
    observed_hash = hashlib.sha256(_canonical_checkpoint_bytes(cp)).hexdigest()
    if observed_hash != payload_hash:
        raise IntegrityViolation(
            run_id=cp.run_id,
            expected_hash=payload_hash,
            observed_hash=observed_hash,
        )


class EncryptedCheckpointStore:
    """Decorator: wraps any CheckpointStore + Cipher; encrypts last_request_json
    + computes full-Checkpoint integrity tag.

    Reads and writes are transparent to DurableWorkflow — the wrapped store
    sees ciphertext in last_request_json + a SEAL:v1: integrity_tag; the
    EncryptedCheckpointStore verifies + decrypts on the way out.
    """

    # Sentinel string prepended to encrypted payloads so decrypt-on-read can
    # detect un-encrypted legacy checkpoints (created before this decorator
    # was wrapped) and pass them through untouched.
    _ENC_PREFIX = "ENC:v1:"
    # A16-M-03 closure: tighten pass-through guard so plaintext starting with
    # ENC:v1: doesn't accidentally short-circuit encryption. Real ciphertext
    # is base64 (Fernet: urlsafe-b64 `A-Za-z0-9_\-=`); JSON `last_request_json`
    # always starts with `{` or `[` and almost never with `ENC:v1:` followed
    # by pure base64 chars. The character-class fullmatch is the safety net.
    _ENC_REMAINDER_RE = re.compile(r"^[A-Za-z0-9_\-=]+$")

    def __init__(
        self,
        inner: Any,
        cipher: Cipher | None = None,
        *,
        cipher_for_tenant: Callable[[str], Cipher] | None = None,
        metrics: Any | None = None,
        workflow_class: str = "unknown",
        refuse_legacy_aead: bool = False,
    ) -> None:
        """D-TENANT-7 (Tier 2.1c): exactly one of `cipher` or `cipher_for_tenant`
        must be provided.

        - `cipher`: single Cipher instance for ALL tenants (single-tenant
          deployments OR a deliberate shared-keyring multi-tenant setup
          accepting the cross-tenant payload-decrypt risk).
        - `cipher_for_tenant`: resolver callable mapping tenant_id → Cipher.
          Invoked per-checkpoint at seal/unseal time. Resolver raises
          `UnknownTenantError` on unknown tenant (fails closed; no fallback).
          Use `functools.lru_cache` on the callable to amortize KMS lookups.
        """
        self._inner = inner
        # Mutual-exclusion check: caller MUST provide exactly one.
        if (cipher is None) == (cipher_for_tenant is None):
            raise ValueError(
                "EncryptedCheckpointStore requires exactly one of "
                "`cipher` or `cipher_for_tenant` (got "
                f"cipher={cipher is not None}, "
                f"cipher_for_tenant={cipher_for_tenant is not None})"
            )
        # Internal resolver — always returns Cipher; for single-cipher case
        # wraps the fixed instance in a closure so call sites have one shape.
        if cipher is not None:
            _fixed = cipher
            self._cipher_for: Callable[[str], Cipher] = lambda _tid: _fixed
            self._has_resolver = False
        else:
            assert cipher_for_tenant is not None  # narrowing for mypy
            self._cipher_for = cipher_for_tenant
            self._has_resolver = True
        # Tier 1.1 Slice A: optional MetricsBackend for decrypt-failure counter.
        # Default Noop so existing callers keep working unchanged.
        if metrics is None:
            from .metrics import NoopMetricsBackend
            metrics = NoopMetricsBackend()
        self._metrics = metrics
        self._workflow_class = workflow_class
        # A16-H-01 closure: post-reseal hardening. When set (via kwarg OR
        # env var DURABLE_REFUSE_LEGACY_AEAD=1, mirroring DURABLE_REFUSE_UNVERSIONED
        # in reseal_all_checkpoints.py), any row read with no integrity_tag
        # is treated as tampering (insider strip attack) rather than a legacy
        # pre-1.9 warning. Operators flip this AFTER a successful reseal sweep.
        self._refuse_legacy_aead = bool(refuse_legacy_aead) or (
            os.environ.get("DURABLE_REFUSE_LEGACY_AEAD") == "1"
        )

    @property
    def inner(self) -> Any:
        """A16-L-04 closure: documented accessor for the wrapped inner store.
        Operator tooling (migrate_schema, reseal_all_checkpoints) should
        prefer ``store.inner`` over reaching into the private ``_inner``."""
        return self._inner

    def _encrypt_request_json(self, cp: Checkpoint) -> Checkpoint:
        # Return a NEW Checkpoint with last_request_json swapped to ciphertext.
        # Do not mutate the caller's instance.
        if cp.last_request_json.startswith(self._ENC_PREFIX):
            # Already encrypted (e.g., re-write after read); pass through.
            # A16-M-03: validate the remainder looks like Fernet ciphertext
            # so plaintext starting with the sentinel doesn't get short-
            # circuited and bricked on subsequent decrypt.
            remainder = cp.last_request_json[len(self._ENC_PREFIX):]
            if remainder and self._ENC_REMAINDER_RE.fullmatch(remainder):
                return cp
            # else fall through and re-encrypt (treat as plaintext that
            # accidentally starts with the sentinel)
        # D-TENANT-7 (Tier 2.1c): resolve cipher per cp.tenant_id. For
        # single-cipher deployments the resolver returns the fixed instance.
        cipher = self._cipher_for(cp.tenant_id)
        ciphertext = cipher.encrypt(cp.last_request_json)
        return Checkpoint(
            run_id=cp.run_id,
            tenant_id=cp.tenant_id,
            schema_version=cp.schema_version,
            status=cp.status,
            round=cp.round,
            rounds_history=cp.rounds_history,
            last_request_json=f"{self._ENC_PREFIX}{ciphertext}",
            pause_reason=cp.pause_reason,
            pause_context=cp.pause_context,
            budget_used=cp.budget_used,
            pinned_executor_model=cp.pinned_executor_model,
            pinned_reviewer_model=cp.pinned_reviewer_model,
            created_at=cp.created_at,
            updated_at=cp.updated_at,
            wake_at=cp.wake_at,
            workflow_version_hash=cp.workflow_version_hash,
            integrity_tag=cp.integrity_tag,
        )

    def _decrypt_request_json(self, cp: Checkpoint) -> Checkpoint:
        if not cp.last_request_json.startswith(self._ENC_PREFIX):
            # Legacy un-encrypted checkpoint; pass through (emit a warning so
            # operator knows the store isn't fully encrypted yet)
            warnings.warn(
                f"EncryptedCheckpointStore.read: run {cp.run_id!r} stored "
                f"WITHOUT encryption prefix; was the store wrapped after this "
                f"checkpoint was written? Plaintext PHI risk per H-DUR-4.",
                UserWarning,
                stacklevel=3,
            )
            return cp
        ciphertext = cp.last_request_json[len(self._ENC_PREFIX):]
        # D-TENANT-7 (Tier 2.1c): resolver picks tenant-scoped Cipher.
        # UnknownTenantError from the resolver propagates as a decrypt failure
        # (counter tag uses "UnknownTenantError" so operators can grep alerts).
        cipher = self._cipher_for(cp.tenant_id)
        try:
            plaintext = cipher.decrypt(ciphertext)
        except Exception as exc:
            # Tier 1.1 Slice A: decrypt-failure counter for rotation-in-progress
            # signal. Tag values are allowlisted low-cardinality strings only;
            # NO key id / fingerprint (per spec §2 threat model).
            self._metrics.counter(
                "durable.cipher.decrypt_failed",
                tags={
                    "workflow": self._workflow_class,
                    "cipher_backend": type(cipher).__name__,
                    "error_class": type(exc).__name__,
                },
            )
            raise
        return Checkpoint(
            run_id=cp.run_id,
            tenant_id=cp.tenant_id,
            schema_version=cp.schema_version,
            status=cp.status,
            round=cp.round,
            rounds_history=cp.rounds_history,
            last_request_json=plaintext,
            pause_reason=cp.pause_reason,
            pause_context=cp.pause_context,
            budget_used=cp.budget_used,
            pinned_executor_model=cp.pinned_executor_model,
            pinned_reviewer_model=cp.pinned_reviewer_model,
            created_at=cp.created_at,
            updated_at=cp.updated_at,
            wake_at=cp.wake_at,
            workflow_version_hash=cp.workflow_version_hash,
            integrity_tag=cp.integrity_tag,
        )

    async def seal(self, checkpoint: Checkpoint) -> Checkpoint:
        """Tier 2.2 (D-API-1): public transform returning the post-encrypt +
        post-integrity-tag form of ``checkpoint`` WITHOUT writing.

        Operator tooling that needs optimistic-concurrency CAS
        (e.g. ``write_if_unchanged`` on the Postgres sibling) should:

            sealed = await store.seal(cp)
            await inner.write_if_unchanged(sealed, expected_updated_at=...)

        Idempotent on already-sealed checkpoints: re-running seal() recomputes
        the tag against current canonical bytes (same result for unchanged
        input).
        """
        encrypted = await asyncio.to_thread(self._encrypt_request_json, checkpoint)
        # Clear any inherited integrity_tag before computing the new one so the
        # canonical bytes don't include a stale tag value.
        unsealed = _replace_integrity_tag(encrypted, None)
        payload = _compute_integrity_payload(unsealed)
        # D-TENANT-7 (Tier 2.1c): integrity tag is signed by the tenant's
        # cipher — cross-tenant tag reuse fails AEAD verification.
        cipher = self._cipher_for(checkpoint.tenant_id)
        tag = await asyncio.to_thread(cipher.encrypt, payload)
        return _replace_integrity_tag(unsealed, tag)

    async def unseal(self, checkpoint: Checkpoint) -> Checkpoint:
        """Tier 2.2 (D-API-1): public transform returning the plaintext form
        of ``checkpoint``. Verifies integrity_tag first (same fail-closed
        semantics as ``read()``), then decrypts field-level.

        Most callers should use ``read(run_id)`` which performs the same
        transform after fetching from the inner store. ``unseal`` is exposed
        for tooling that walks the inner store directly.
        """
        if not checkpoint.integrity_tag:
            if self._refuse_legacy_aead:
                raise IntegrityViolation(
                    run_id=checkpoint.run_id,
                    expected_hash="<no-tag-but-refuse-legacy-enabled>",
                    observed_hash="<empty>",
                )
            warnings.warn(
                f"EncryptedCheckpointStore.unseal: run {checkpoint.run_id!r} "
                f"has no integrity_tag (pre-1.9 row, A10-H2). Run "
                f"reseal_all_checkpoints.py to upgrade.",
                LegacyPartialAEADWarning,
                stacklevel=3,
            )
        else:
            # D-TENANT-7 (Tier 2.1c): resolve cipher for the row's tenant.
            # UnknownTenantError from the resolver propagates BEFORE the try
            # so it isn't counted as a decrypt-failure (it's a config issue).
            cipher = self._cipher_for(checkpoint.tenant_id)
            try:
                payload = await asyncio.to_thread(
                    cipher.decrypt, checkpoint.integrity_tag
                )
            except IntegrityViolation:
                raise
            except Exception as exc:
                self._metrics.counter(
                    "durable.cipher.decrypt_failed",
                    tags={
                        "workflow": self._workflow_class,
                        "cipher_backend": type(cipher).__name__,
                        "error_class": type(exc).__name__,
                    },
                )
                raise
            _verify_integrity_payload(payload, checkpoint)
        return await asyncio.to_thread(self._decrypt_request_json, checkpoint)

    async def write(self, checkpoint: Checkpoint) -> None:
        # Encrypt field-level first, then seal the post-encryption form so the
        # integrity tag binds to bytes actually persisted (A10-H2 closure).
        sealed = await self.seal(checkpoint)
        await self._inner.write(sealed)

    async def read(self, run_id: str) -> Checkpoint:
        cp = await self._inner.read(run_id)
        return await self.unseal(cp)

    async def list_paused(self, wake_before: datetime) -> list[ResumeToken]:
        # list_paused returns ResumeToken (not Checkpoint), and ResumeToken
        # carries no encrypted fields — pass through.
        result: list[ResumeToken] = await self._inner.list_paused(wake_before=wake_before)
        return result

    async def delete(self, run_id: str) -> None:
        await self._inner.delete(run_id)
