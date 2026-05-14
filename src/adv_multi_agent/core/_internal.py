"""
Internal utilities shared across core, workflows, and assurance.

- parse_first_json:    safely extract the first valid JSON object/array
- atomic_write_text:   write file via temp+rename (durable, no torn writes)
- redact_secret:       fixed-shape redaction of API keys for logs
- coerce_score:        clamp a numeric value to [0, 10] and reject inf/NaN
- safe_resolve_path:   resolve a user-supplied path, optionally constrained to a base
- sanitize_for_prompt: strip control chars and cap length before embedding in prompts
- extract_flags:       parse a named FLAGS section out of a reviewer critique
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
_PARSE_FIRST_JSON_MAX_CHARS = 65_536


def parse_first_json(text: str) -> Any:
    """
    Return the first syntactically valid JSON object or array in `text`.

    Uses `JSONDecoder.raw_decode` from the first `{` or `[`. Prefers the
    earliest valid object over the longest brace-span, so attacker-controlled
    JSON appearing later in the response cannot dominate a greedy match.

    Raises ValueError if no valid JSON value is found, or if `text` exceeds
    the safety cap (H6: bound worst-case O(N^2) raw_decode scan triggered by
    adversarial opener-only inputs like `[[[[...`).
    """
    if len(text) > _PARSE_FIRST_JSON_MAX_CHARS:
        raise ValueError(
            f"input length {len(text)} exceeds max {_PARSE_FIRST_JSON_MAX_CHARS} chars"
        )
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
    of the original — full opacity. L6: empty/unset secrets return the
    same token as set ones to avoid leaking presence/absence via logs.
    """
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
_SAFE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


def is_safe_id(value: Any) -> bool:
    """
    Return True if `value` is a string matching the safe-id charset:
    1-64 chars of [A-Za-z0-9_-]. Used by Claim/WikiEntry.from_dict (H5)
    to refuse attacker-controlled ids loaded from disk before they reach
    reviewer prompts (e.g. via `[{c.id}]` formatting in verifier).
    """
    return isinstance(value, str) and bool(_SAFE_ID_RE.match(value))


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


def extract_flags(critique: str, header: str) -> list[str]:
    """
    Parse a named FLAGS section out of a reviewer critique.

    Returns the list of bullet items under `header`, stopping at the next
    section header. A section header is any of:

    • a line starting with `Overall`, `Key issues`, or a markdown `#`
    • a bare uppercase-with-colon header (e.g. `SCOPE FLAGS:`)
    • an inline uppercase header on the same line
      (e.g. `EVIDENCE FLAGS: None detected`, `REVIEWER VETO: ...`) —
      recognised by the LHS of the first `:` being uppercase + spaces only.

    Returns `[]` if the header is absent, or if the section content is one
    of the conventional empty markers: `None detected`, `None`, `n/a`
    (case-insensitive).

    Used by retail workflows (`recall_scope`, `loyalty_offer`,
    `promo_markdown`) that share a multi-flag review-output structure.
    `demand_forecasting` and `labor_scheduling` use simpler inline parsers
    by design — their critique structure only has one flag class so the
    inline-header stop is not needed.
    """
    # Anchor the header at line-start (allowing leading whitespace) to
    # avoid mis-anchoring on a commentary mention of the header name earlier
    # in the critique (M1 — substring containment regression).
    match = re.search(rf"(?m)^\s*{re.escape(header)}", critique)
    if match is None:
        return []
    section = critique[match.end():]
    flags: list[str] = []
    for raw_line in section.splitlines():
        stripped_raw = raw_line.strip()
        stripped = stripped_raw.lstrip("-•*").strip()
        if not stripped:
            continue
        lower = stripped.lower()
        if lower.startswith(("overall", "key issues", "#")):
            break
        if ":" in stripped_raw:
            lhs = stripped_raw.split(":", 1)[0].strip()
            if lhs and lhs.replace(" ", "").isalpha() and lhs.isupper():
                break
        if lower in ("none detected", "none", "n/a"):
            return []
        flags.append(stripped)
    return flags
