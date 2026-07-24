"""anchor_audit_chain.py — Tier 3.1 WORM chain-head anchor (D-AUDIT-8).

Design: docs/superpowers/specs/2026-07-23-durable-audit-log-design.md §5.2.

Periodically (cron) writes each per-tenant chain head (max seq + its row_hash)
to a WORM object store with Object-Lock COMPLIANCE retention. This is the ONLY
layer that catches a DB admin / superuser rewriting the whole chain: an
adversary with UPDATE/DELETE can rewrite `audit_log` and recompute every
`prev_hash`, but cannot delete/overwrite an existing locked anchor object nor
backdate its server-assigned creation time. The walker (verify_audit_chain.py)
trusts the earliest anchor covering each seq.

Trust assumption (stated in the design §2): Object-Lock COMPLIANCE forbids
delete/overwrite before retention expiry AND the object's server-side
creation-time is unforgeable. S3 Object Lock in COMPLIANCE mode gives both — not
even the account root can shorten retention or alter a locked object.

RFC-3161 TSA is the documented alternative anchor (§10): swap `write_anchor` for
a TSA submit + store the signed token; the walker's earliest-time-wins logic is
unchanged. Not built.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any


def build_anchor_record(
    tenant_id: str, seq: int, row_hash: str, head_at: str, anchored_at: str
) -> dict[str, Any]:
    """Pure: the JSON body of an anchor object. Kept small + stable so a diff
    across anchor runs is meaningful."""
    return {
        "tenant_id": tenant_id,
        "seq": int(seq),
        "row_hash": row_hash,
        "head_at": head_at,
        "anchored_at": anchored_at,
    }


def anchor_object_key(prefix: str, tenant_id: str, anchored_at: str) -> str:
    """S3/GCS object key. One object per anchor run per tenant; server-side
    creation time is the trusted timestamp (do NOT trust `anchored_at` in the
    body — it is app-supplied and only informational)."""
    safe_ts = anchored_at.replace(":", "").replace("+", "Z")
    return f"{prefix.rstrip('/')}/{tenant_id}/{safe_ts}.json"


# --- S3 WORM backend (primary) --------------------------------------------

def _s3_client() -> Any:  # pragma: no cover - requires boto3 + creds
    import boto3

    return boto3.client("s3")


def write_anchor_s3(
    bucket: str, prefix: str, record: dict[str, Any], retain_days: int
) -> str:  # pragma: no cover - I/O
    """PUT one anchor object with Object-Lock COMPLIANCE retention. Requires the
    bucket to have Object Lock enabled. Returns the object key."""
    from datetime import datetime, timedelta, timezone

    key = anchor_object_key(prefix, record["tenant_id"], record["anchored_at"])
    retain_until = datetime.now(timezone.utc) + timedelta(days=retain_days)
    _s3_client().put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(record, sort_keys=True).encode("utf-8"),
        ObjectLockMode="COMPLIANCE",
        ObjectLockRetainUntilDate=retain_until,
        ContentType="application/json",
    )
    return key


def read_all_anchors(tenant_id: str) -> list[dict[str, Any]]:  # pragma: no cover - I/O
    """Read EVERY retained anchor for a tenant, tagging each with the WORM
    store's server-side creation time as `created_at` (the walker trusts this,
    NOT the body's `anchored_at`). Used by verify_audit_chain.py.

    Backend selected by env: AUDIT_ANCHOR_BUCKET (+ AUDIT_ANCHOR_PREFIX) → S3;
    else AUDIT_ANCHOR_DIR → local dir (DEV ONLY — a local dir is NOT WORM and
    provides no superuser protection; refuse it in prod)."""
    bucket = os.environ.get("AUDIT_ANCHOR_BUCKET")
    prefix = os.environ.get("AUDIT_ANCHOR_PREFIX", "audit-anchors")
    if bucket:
        s3 = _s3_client()
        out: list[dict[str, Any]] = []
        paginator = s3.get_paginator("list_objects_v2")
        for page in paginator.paginate(Bucket=bucket, Prefix=f"{prefix}/{tenant_id}/"):
            for obj in page.get("Contents", []):
                body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
                rec = json.loads(body)
                # LastModified = server-assigned; immutable under Object Lock.
                rec["created_at"] = obj["LastModified"].isoformat()
                out.append(rec)
        return out

    local_dir = os.environ.get("AUDIT_ANCHOR_DIR")
    if local_dir:
        if os.environ.get("AUDIT_ALLOW_LOCAL_ANCHOR") != "1":
            raise RuntimeError(
                "AUDIT_ANCHOR_DIR is a DEV-ONLY non-WORM backend; set "
                "AUDIT_ALLOW_LOCAL_ANCHOR=1 to acknowledge it gives NO superuser "
                "protection, or configure AUDIT_ANCHOR_BUCKET for real WORM."
            )
        out = []
        tdir = os.path.join(local_dir, tenant_id)
        if os.path.isdir(tdir):
            for name in os.listdir(tdir):
                path = os.path.join(tdir, name)
                with open(path, encoding="utf-8") as fh:
                    rec = json.load(fh)
                rec["created_at"] = (
                    __import__("datetime").datetime.utcfromtimestamp(
                        os.path.getmtime(path)
                    ).isoformat()
                )
                out.append(rec)
        return out

    raise RuntimeError("no anchor backend: set AUDIT_ANCHOR_BUCKET or AUDIT_ANCHOR_DIR")


async def _amain() -> int:  # pragma: no cover - I/O driver
    import asyncpg

    dsn = os.environ.get("AUDIT_DATABASE_URL") or os.environ.get("DATABASE_URL")
    bucket = os.environ.get("AUDIT_ANCHOR_BUCKET")
    prefix = os.environ.get("AUDIT_ANCHOR_PREFIX", "audit-anchors")
    retain_days = int(os.environ.get("AUDIT_ANCHOR_RETAIN_DAYS", "2557"))  # ~7y default
    if not dsn or not bucket:
        print("set AUDIT_DATABASE_URL and AUDIT_ANCHOR_BUCKET", file=sys.stderr)
        return 2
    from datetime import datetime, timezone

    conn = await asyncpg.connect(dsn)
    try:
        heads = await conn.fetch(
            """
            SELECT DISTINCT ON (tenant_id) tenant_id, seq, row_hash, at
            FROM audit_log ORDER BY tenant_id, seq DESC
            """
        )
        now = datetime.now(timezone.utc).isoformat()
        for h in heads:
            rec = build_anchor_record(
                h["tenant_id"], int(h["seq"]), str(h["row_hash"]), str(h["at"]), now
            )
            key = write_anchor_s3(bucket, prefix, rec, retain_days)
            print(f"anchored {h['tenant_id']} seq={h['seq']} -> {key}")
    finally:
        await conn.close()
    return 0


if __name__ == "__main__":  # pragma: no cover
    import asyncio

    raise SystemExit(asyncio.run(_amain()))
