"""RunLock — exclusive lock for a run_id, with TTL and heartbeat.

POC ships FileRunLock (atomic-rename `<run_id>.lock` file with mtime as
acquisition timestamp) and MemoryRunLock (in-process dict).

Production swap candidates: PostgresAdvisoryLock (pg_try_advisory_lock),
RedisRunLock (Redlock pattern), DynamoConditionalLock. Same Protocol.
"""
from __future__ import annotations

import os
import time
from dataclasses import dataclass
from pathlib import Path

from .._internal import safe_resolve_path


class RunLocked(RuntimeError):
    """Raised when an already-held lock is requested."""

    def __init__(self, run_id: str, locked_at: float) -> None:
        super().__init__(f"run {run_id!r} locked since {locked_at}")
        self.run_id = run_id
        self.locked_at = locked_at


@dataclass(frozen=True)
class LockHandle:
    run_id: str
    acquired_at: float
    ttl_seconds: int


class MemoryRunLock:
    def __init__(self) -> None:
        self._locks: dict[str, LockHandle] = {}

    def _is_stale(self, h: LockHandle, now: float) -> bool:
        return (now - h.acquired_at) >= h.ttl_seconds

    async def acquire(self, run_id: str, ttl_seconds: int) -> LockHandle:
        now = time.monotonic()
        existing = self._locks.get(run_id)
        if existing is not None and not self._is_stale(existing, now):
            raise RunLocked(run_id, existing.acquired_at)
        handle = LockHandle(run_id=run_id, acquired_at=now, ttl_seconds=ttl_seconds)
        self._locks[run_id] = handle
        return handle

    async def release(self, handle: LockHandle) -> None:
        existing = self._locks.get(handle.run_id)
        if existing is not None and existing.acquired_at == handle.acquired_at:
            self._locks.pop(handle.run_id, None)

    async def heartbeat(self, handle: LockHandle) -> None:
        existing = self._locks.get(handle.run_id)
        if existing is None or existing.acquired_at != handle.acquired_at:
            return
        self._locks[handle.run_id] = LockHandle(
            run_id=handle.run_id,
            acquired_at=time.monotonic(),
            ttl_seconds=handle.ttl_seconds,
        )


class FileRunLock:
    def __init__(self, base_dir: Path | str) -> None:
        resolved = safe_resolve_path(Path(base_dir))
        resolved.mkdir(parents=True, exist_ok=True)
        self._base_dir = resolved

    def _path(self, run_id: str) -> Path:
        if not run_id.replace("-", "").isalnum():
            raise ValueError(f"invalid run_id charset: {run_id!r}")
        return self._base_dir / f"{run_id}.lock"

    def _read_stored_ttl(self, path: Path) -> int | None:
        """Read the TTL written at acquisition. Returns None if unreadable."""
        try:
            content = path.read_text(encoding="utf-8").strip()
        except (OSError, FileNotFoundError):
            return None
        # File format: "<acquired_at>\n<ttl_seconds>"
        parts = content.split("\n")
        if len(parts) < 2:
            return None
        try:
            return int(parts[1])
        except ValueError:
            return None

    async def acquire(self, run_id: str, ttl_seconds: int) -> LockHandle:
        path = self._path(run_id)
        now = time.time()
        if path.exists():
            mtime = path.stat().st_mtime
            stored_ttl = self._read_stored_ttl(path)
            # Use the TTL of the holder, not the requester. Falls back to the
            # requester's ttl_seconds if the file is unreadable (defensive).
            effective_ttl = stored_ttl if stored_ttl is not None else ttl_seconds
            if (now - mtime) < effective_ttl:
                raise RunLocked(run_id, mtime)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        try:
            fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError as exc:
            raise RunLocked(run_id, path.stat().st_mtime) from exc
        os.write(fd, f"{now}\n{ttl_seconds}".encode("utf-8"))
        os.close(fd)
        # Stamp mtime explicitly so file timestamp matches handle.acquired_at
        # (Windows file mtime can otherwise advance past `now` between open+write,
        # breaking TTL math when ttl_seconds is small).
        try:
            os.utime(str(path), (now, now))
        except FileNotFoundError:
            pass
        return LockHandle(run_id=run_id, acquired_at=now, ttl_seconds=ttl_seconds)

    async def release(self, handle: LockHandle) -> None:
        path = self._path(handle.run_id)
        try:
            if path.exists() and abs(path.stat().st_mtime - handle.acquired_at) < 1.0:
                path.unlink()
        except FileNotFoundError:
            pass

    async def heartbeat(self, handle: LockHandle) -> None:
        path = self._path(handle.run_id)
        if not path.exists():
            return
        now = time.time()
        try:
            os.utime(str(path), (now, now))
        except FileNotFoundError:
            return
