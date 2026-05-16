"""RunLock — exclusive lock for a run_id, with TTL and heartbeat.

POC ships FileRunLock (OS-level advisory file lock via fcntl/msvcrt) and
MemoryRunLock (in-process dict).

Production swap candidates: PostgresAdvisoryLock (pg_try_advisory_lock),
RedisRunLock (Redlock pattern), DynamoConditionalLock. Same Protocol.
"""
from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .._internal import safe_resolve_path

# M-DUR-3: TTL bounds for run-lock acquisition
_MIN_TTL = 1
_MAX_TTL = 86400


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
        if not (_MIN_TTL <= ttl_seconds <= _MAX_TTL):
            raise ValueError(
                f"ttl_seconds={ttl_seconds} out of range [{_MIN_TTL}, {_MAX_TTL}]"
            )
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


# Platform-specific advisory file locking
if sys.platform == "win32":
    import msvcrt

    def _try_lock_fd(fd: int) -> bool:
        """Try exclusive advisory lock; True on success, False if held."""
        try:
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def _unlock_fd(fd: int) -> None:
        try:
            os.lseek(fd, 0, 0)
            msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
        except OSError:
            pass
else:
    import fcntl

    def _try_lock_fd(fd: int) -> bool:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            return False

    def _unlock_fd(fd: int) -> None:
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        except OSError:
            pass


class FileRunLock:
    """OS-level advisory file lock keyed on `<base_dir>/<run_id>.lock`.

    Mutual exclusion is enforced by `fcntl.flock` (POSIX) or `msvcrt.locking`
    (Windows), not by mtime comparison. The lock is released when the FD
    closes, which happens on explicit release(), process exit, or crash —
    no stale-eviction race (M-DUR-2 closed).

    `ttl_seconds` is advisory: stored in the lock file for diagnostics and
    surfaces as `RunLocked.locked_at` in error messages. The OS, not the
    TTL, governs reclaim.

    Args:
        base_dir: directory under which per-run lock files land.
        workspace_dir: if provided, base_dir is confined under it via
            safe_resolve_path. If None, emits a UserWarning (H-DUR-3).
    """

    # Track open FDs keyed by (run_id, acquired_at) so release/heartbeat
    # can find them. Class-level so the same lock instance survives moves.
    _open_fds: "dict[tuple[str, float], int]" = {}

    def __init__(
        self,
        base_dir: Path | str,
        *,
        workspace_dir: Path | str | None = None,
    ) -> None:
        if workspace_dir is None:
            import warnings
            warnings.warn(
                "FileRunLock constructed without workspace_dir; "
                "base_dir is not sandboxed. Pass workspace_dir=<trusted root> "
                "to confine lock files (security finding H-DUR-3).",
                UserWarning,
                stacklevel=2,
            )
            resolved = safe_resolve_path(Path(base_dir))
        else:
            workspace = safe_resolve_path(Path(workspace_dir))
            resolved = safe_resolve_path(Path(base_dir), must_be_under=workspace)
        resolved.mkdir(parents=True, exist_ok=True)
        self._base_dir = resolved

    def _path(self, run_id: str) -> Path:
        if not run_id.replace("-", "").isalnum():
            raise ValueError(f"invalid run_id charset: {run_id!r}")
        return self._base_dir / f"{run_id}.lock"

    async def acquire(self, run_id: str, ttl_seconds: int) -> LockHandle:
        if not (_MIN_TTL <= ttl_seconds <= _MAX_TTL):
            raise ValueError(
                f"ttl_seconds={ttl_seconds} out of range [{_MIN_TTL}, {_MAX_TTL}]"
            )
        path = self._path(run_id)
        now = time.time()
        # Open shared inode in RW; OS lock arbitrates regardless of creator.
        fd = os.open(str(path), os.O_CREAT | os.O_RDWR, 0o600)
        if not _try_lock_fd(fd):
            os.close(fd)
            # Best-effort: read holder's acquired_at for diagnostic
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = f.read().strip()
                holder_at = float(raw.split("\n")[0]) if raw else 0.0
            except (OSError, ValueError):
                holder_at = 0.0
            raise RunLocked(run_id, holder_at)
        # Write holder metadata for diagnostics (lock is what matters)
        try:
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, 0)
            os.write(fd, f"{now}\n{ttl_seconds}\n".encode("utf-8"))
        except OSError:
            pass
        handle = LockHandle(run_id=run_id, acquired_at=now, ttl_seconds=ttl_seconds)
        FileRunLock._open_fds[(run_id, handle.acquired_at)] = fd
        return handle

    async def release(self, handle: LockHandle) -> None:
        key = (handle.run_id, handle.acquired_at)
        fd = FileRunLock._open_fds.pop(key, None)
        if fd is None:
            return
        _unlock_fd(fd)
        try:
            os.close(fd)
        except OSError:
            pass
        # Best-effort cleanup of the lock file.
        try:
            self._path(handle.run_id).unlink()
        except (FileNotFoundError, PermissionError, OSError):
            pass

    async def heartbeat(self, handle: LockHandle) -> None:
        key = (handle.run_id, handle.acquired_at)
        fd = FileRunLock._open_fds.get(key)
        if fd is None:
            return
        # Refresh acquired_at written to the file (diagnostic only)
        try:
            now = time.time()
            os.ftruncate(fd, 0)
            os.lseek(fd, 0, 0)
            os.write(fd, f"{now}\n{handle.ttl_seconds}\n".encode("utf-8"))
        except OSError:
            pass
