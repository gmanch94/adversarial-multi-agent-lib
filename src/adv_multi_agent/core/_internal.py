"""
Internal utilities shared across core, workflows, and assurance.

- parse_first_json:    safely extract the first valid JSON object/array
- atomic_write_text:   write file via temp+rename (durable, no torn writes)
- redact_secret:       fixed-shape redaction of API keys for logs
- coerce_score:        clamp a numeric value to [0, 10] and reject inf/NaN
- safe_resolve_path:   resolve a user-supplied path, optionally constrained to a base
- sanitize_for_prompt: strip control chars and cap length before embedding in prompts
"""
from __future__ import annotations

import json
import math
import os
import re
import tempfile
import unicodedata
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# JSON parsing — replaces every greedy DOTALL regex (CRIT-3)
# ---------------------------------------------------------------------------

_JSON_START = re.compile(r"[\{\[]")


def parse_first_json(text: str) -> Any:
    """
    Return the first syntactically valid JSON object or array in `text`.

    Uses `JSONDecoder.raw_decode` from the first `{` or `[`. Prefers the
    earliest valid object over the longest brace-span, so attacker-controlled
    JSON appearing later in the response cannot dominate a greedy match.

    Raises ValueError if no valid JSON value is found.
    """
    decoder = json.JSONDecoder()
    pos = 0
    while pos < len(text):
        match = _JSON_START.search(text, pos)
        if match is None:
            break
        start = match.start()
        try:
            value, _ = decoder.raw_decode(text, start)
        except json.JSONDecodeError:
            pos = start + 1
            continue
        return value
    raise ValueError("no valid JSON object found in text")


def parse_first_json_or(text: str, default: Any) -> Any:
    """Same as parse_first_json but returns `default` on failure."""
    try:
        return parse_first_json(text)
    except ValueError:
        return default


# ---------------------------------------------------------------------------
# Atomic file writes — HIGH-4
# ---------------------------------------------------------------------------

def atomic_write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    """
    Write `content` to `path` atomically: write to a tempfile in the same
    directory, fsync, then os.replace() onto the target. Eliminates torn-write
    corruption on crash or interrupt.
    """
    path = Path(path)
    parent = path.parent
    parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_str = tempfile.mkstemp(
        prefix=f".{path.name}.", suffix=".tmp", dir=str(parent)
    )
    tmp = Path(tmp_str)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass  # fsync not supported on every fs; replace is still atomic
        os.replace(tmp, path)
    except Exception:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# Secret redaction — CRIT-1
# ---------------------------------------------------------------------------

def redact_secret(value: str) -> str:
    """
    Return a fixed-shape redaction of a secret. Never returns any portion
    of the original — full opacity. Empty/unset secrets are reported as such.
    """
    if not value:
        return "<unset>"
    return "<redacted>"


# ---------------------------------------------------------------------------
# Numeric coercion — HIGH-1
# ---------------------------------------------------------------------------

def coerce_score(value: Any, default: float = 0.0) -> float:
    """
    Convert `value` to a float clamped to [0.0, 10.0]. Rejects NaN and inf.
    Falls back to `default` on any parse failure.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return default
    if math.isnan(f) or math.isinf(f):
        return default
    return max(0.0, min(10.0, f))


# ---------------------------------------------------------------------------
# Path validation — LOW-6, HIGH-5
# ---------------------------------------------------------------------------

def safe_resolve_path(path: str | Path, must_be_under: str | Path | None = None) -> Path:
    """
    Resolve `path` to an absolute Path. If `must_be_under` is supplied, raise
    ValueError if the resolved path is not inside that base.
    """
    resolved = Path(path).expanduser().resolve()
    if must_be_under is not None:
        base = Path(must_be_under).expanduser().resolve()
        try:
            resolved.relative_to(base)
        except ValueError as exc:
            raise ValueError(
                f"path {resolved} is outside the allowed base {base}"
            ) from exc
    return resolved


# ---------------------------------------------------------------------------
# Prompt content sanitization — HIGH-2, HIGH-3, MED-3, MED-7
# ---------------------------------------------------------------------------

_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


def sanitize_for_prompt(text: str, max_chars: int = 2000) -> str:
    """
    Strip control characters, NFC-normalize, and truncate to `max_chars`.
    Used before embedding model-derived or user-supplied content in prompts
    to limit obvious prompt-injection vectors and bound prompt size.
    """
    if not isinstance(text, str):
        text = str(text)
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL_CHARS_RE.sub("", text)
    if len(text) > max_chars:
        text = text[:max_chars] + "...[truncated]"
    return text
