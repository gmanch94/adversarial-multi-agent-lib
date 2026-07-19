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
import sys
import tempfile
import unicodedata
import warnings
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
        # L-DUR-3: on POSIX, fsync the parent directory so the rename is
        # durable across power loss. Windows doesn't support dir fsync; skip.
        if sys.platform != "win32":
            try:
                dir_fd = os.open(str(parent), os.O_RDONLY)
                try:
                    os.fsync(dir_fd)
                finally:
                    os.close(dir_fd)
            except OSError:
                pass  # FS without dir-fsync support; best effort
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
# L2: bound the number of flag bullets returned per header. The 4000-char
# critique cap upstream already bounds worst-case at ~hundreds, but an
# explicit cap is defence-in-depth against prompt-bloat from a malicious
# or pathological reviewer output.
_MAX_FLAGS_PER_HEADER = 64


def is_safe_id(value: Any) -> bool:
    """
    Return True if `value` is a string matching the safe-id charset:
    1-64 chars of [A-Za-z0-9_-]. Used by Claim/WikiEntry.from_dict (H5)
    to refuse attacker-controlled ids loaded from disk before they reach
    reviewer prompts (e.g. via `[{c.id}]` formatting in verifier).
    """
    return isinstance(value, str) and bool(_SAFE_ID_RE.match(value))


def cap_field(value: str, max_chars: int, field_name: str = "") -> str:
    """Cap a single Request field to *max_chars* and emit a UserWarning if
    truncation occurs (L-IND-5).

    Use this in ``to_prompt_text`` instead of bare ``value[:max_chars]`` so
    callers who pass oversized inputs see a runtime diagnostic rather than
    silent data loss.  The truncated string does NOT append an ellipsis — the
    raw slice is returned so downstream ``sanitize_for_prompt`` can optionally
    append its own marker.

    Existing workflows that use ``value[:_MAX_FIELD_CHARS]`` directly remain
    correct but silent.  New workflows should use this helper.
    """
    if len(value) > max_chars:
        label = f" ({field_name!r})" if field_name else ""
        warnings.warn(
            f"Request field{label} truncated from {len(value)} to {max_chars} chars "
            f"before prompt injection. Input beyond char {max_chars} will not be "
            f"seen by the model. Verify upstream data quality.",
            UserWarning,
            stacklevel=2,
        )
        return value[:max_chars]
    return value


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


# H-IND-1: sibling-header detection. Accepts uppercase letters, spaces, and
# hyphens in the LHS of a `HEADER:` line. The prior rule used
# `lhs.replace(" ", "").isalpha()`, which rejected hyphens — so hyphen-
# containing peer headers (`IP-LEAK FLAGS:`, `DESIGN-DEFECT FLAGS:`,
# `KNOWN-CONDITION FLAGS:`, etc.) were NOT recognised as section terminators
# and the parser slurped subsequent sibling sections into the prior list.
# Allowing `-` (and trailing space tolerance via `+`) closes the slurp for
# every existing and future flag-header naming convention without loosening
# the alpha-only-uppercase requirement on the rest of the LHS.
_SIBLING_HEADER_LHS_RE = re.compile(r"^[A-Z][A-Z\s\-]*[A-Z]$|^[A-Z]$")


def _is_sibling_header_lhs(lhs: str) -> bool:
    """Return True iff `lhs` is an uppercase-with-optional-hyphen-and-space
    header LHS that should terminate a flag/veto-continuation parse.

    Examples that return True:
      "PRECEDENT FLAGS", "DESIGN-DEFECT FLAGS", "REVIEWER VETO", "F"
    Examples that return False:
      "Overall score", "Key issues", "", "  ", "123 FLAGS"
    """
    return bool(_SIBLING_HEADER_LHS_RE.match(lhs))


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

    Used by every retail workflow (`recall_scope`, `loyalty_offer`,
    `promo_markdown`, `demand_forecasting`, `labor_scheduling`) plus the pc /
    industrial / healthcare domains. `demand_forecasting` and
    `labor_scheduling` were migrated off private single-class parsers to this
    shared helper (2026-07-18) so they inherit the M1 line-anchor and H-IND-1
    sibling-stop fixes; single-flag-class callers simply pass their one header.
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
            if lhs and _is_sibling_header_lhs(lhs):
                break
        if lower in ("none detected", "none", "n/a"):
            return []
        flags.append(stripped)
        if len(flags) >= _MAX_FLAGS_PER_HEADER:
            break
    return flags


# ---------------------------------------------------------------------------
# Flag re-injection display cap (L-PC-5)
# ---------------------------------------------------------------------------

# Maximum number of flag bullets that may be re-injected into the next-round
# executor prompt via `_format_flag_section`. The upstream `extract_flags`
# already caps at _MAX_FLAGS_PER_HEADER=64; this is a tighter cap on the
# DISPLAY/RE-INJECTION path. Metadata (`accumulated[header]`) keeps all
# accumulated flags for audit-trail purposes; only the next-round prompt is
# truncated.
_MAX_FLAGS_DISPLAYED = 16


def truncate_flag_display(flags: list[str]) -> list[str]:
    """
    Cap a per-header flag list at `_MAX_FLAGS_DISPLAYED` for re-injection
    into the next-round executor prompt. If the list is longer, append a
    single truncation marker so the executor knows entries were elided.

    Audit-trail callers (`metadata['*_flags']`, `accumulated[header]`)
    should NOT route through this helper — they must keep the full list.
    """
    if len(flags) <= _MAX_FLAGS_DISPLAYED:
        return flags
    extra = len(flags) - _MAX_FLAGS_DISPLAYED
    return flags[:_MAX_FLAGS_DISPLAYED] + [f"... ({extra} more truncated)"]


# ---------------------------------------------------------------------------
# Veto directive extraction — shared by every reviewer-veto workflow
# (M-PC-1: line-anchored marker match closes substring-containment regression
#  on the criteria-quote case; M2 / L5 hardening preserved in the continuation
#  loop. Replaces 5 byte-identical static-method copies.)
# ---------------------------------------------------------------------------

def extract_veto_directive(
    critique: str,
    marker: str = "REVIEWER VETO:",
    max_chars: int = 1000,
) -> str | None:
    """
    Parse a verbatim veto directive from a reviewer critique.

    The marker is anchored to line-start (allowing leading whitespace) so a
    commentary mention of the marker name earlier in the critique — e.g. a
    reviewer quoting the criteria block — does NOT mis-anchor the parser
    (M-PC-1: same shape as the M1 fix that line-anchored `extract_flags`).

    Returns the verbatim directive, with leading bullet markers stripped from
    continuation lines and trailing sibling-header sections excluded.
    Returns None if:
    - The marker is not present at line-start.
    - The marker line value is one of the no-veto tokens (`none`,
      `none detected`, `n/a`, case-insensitive) AND no continuation lines
      follow it (M2: a continuation directive after a "none" marker is
      still captured).
    - All continuation lines are empty or are sibling section headers.

    Sibling-header detection uses the L5-hardened rule
    (`lhs.replace(" ", "").isalpha() and lhs.isupper()`) — rejects mixed-
    case AND digit/punctuation-only colon lines.

    The returned directive is truncated to `max_chars`.
    """
    # NOTE: trailing whitespace eater is `[ \t]*` (horizontal whitespace
    # only) — `\s*` would greedily consume the newline and pull the first
    # continuation line into match.group(1), then trigger a premature break
    # on the now-empty post-match line.
    match = re.search(rf"(?m)^[ \t]*{re.escape(marker)}[ \t]*(.*)$", critique)
    if match is None:
        return None

    first_line = match.group(1).strip()
    rest = critique[match.end():]

    collected: list[str] = []
    if first_line and first_line.lower() not in ("none", "none detected", "n/a"):
        collected.append(first_line)

    for raw in rest.splitlines():
        line = raw.strip()
        if not line:
            if collected:
                break
            continue
        lower = line.lower()
        sibling_header = False
        if line.endswith(":"):
            lhs = line[:-1]
            # H-IND-1: also recognises hyphen-containing sibling headers.
            if lhs and _is_sibling_header_lhs(lhs):
                sibling_header = True
        if lower.startswith(("overall", "key issues", "#")) or sibling_header:
            break
        collected.append(line.lstrip("-•*").strip())

    if not collected:
        return None
    veto = " ".join(collected)
    if len(veto) > max_chars:
        veto = veto[:max_chars]
    return veto
