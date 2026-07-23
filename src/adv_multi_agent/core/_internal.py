"""
Internal utilities shared across core, workflows, and assurance.

- parse_first_json:    safely extract the first valid JSON object/array
- atomic_write_text:   write file via temp+rename (durable, no torn writes)
- redact_secret:       fixed-shape redaction of API keys for logs
- coerce_score:        clamp a numeric value to [0, 10] and reject inf/NaN
- safe_resolve_path:   resolve a user-supplied path, optionally constrained to a base
- sanitize_for_prompt: strip control chars and cap length before embedding in prompts
- extract_flags:       parse a named FLAGS section out of a reviewer critique
- missing_flag_headers: which flag sections the reviewer never emitted (A11-M1)
"""
from __future__ import annotations

import json
import math
import os
import re
import sys
import tempfile
import unicodedata
from collections.abc import Iterable
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


_TRUNCATION_MARKER = "...[truncated]"


def sanitize_for_prompt(text: str, max_chars: int = 2000) -> str:
    """
    Strip control characters, NFC-normalize, and truncate to `max_chars`.
    Used before embedding model-derived or user-supplied content in prompts
    to limit obvious prompt-injection vectors and bound prompt size.

    The return value NEVER exceeds `max_chars` (A11-M3). The marker is written
    INSIDE the budget, not appended after a full-width slice: the previous form
    returned `max_chars + 14`, and every one of the 60 `wiki.add_feedback`
    call sites feeds this straight into `ResearchWiki._bound(max_chars)`, which
    RAISES rather than truncates. Any reviewer critique longer than
    `Config.max_wiki_body_chars` therefore aborted `run()` with a ValueError
    and lost that round's audit trail.
    """
    if not isinstance(text, str):
        text = str(text)
    text = unicodedata.normalize("NFC", text)
    text = _CONTROL_CHARS_RE.sub("", text)
    if len(text) > max_chars:
        if max_chars <= len(_TRUNCATION_MARKER):
            text = text[:max_chars]
        else:
            text = text[: max_chars - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
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


# A11-M1 / A11-M5: reviewer models do not reliably emit a bare `HEADER:` at
# line start. Every deviation below used to produce NO match, hence an empty
# flag list, which the convergence gate reads as "no flags" — FAIL-OPEN, the
# safety class is silently unenforced:
#     **SCOPE FLAGS:**   - SCOPE FLAGS:   1. SCOPE FLAGS:
#     SCOPE FLAGS :      Scope flags:
# The anchor now tolerates leading bullets/numbering, markdown emphasis,
# flexible internal and pre-colon whitespace, and case. It remains anchored to
# line start (M1 / M-PC-1) so a mid-line commentary mention cannot mis-anchor.
_HEADER_PREFIX = r"[ \t]*(?:[-*•+]\s*)?(?:\d+[.)]\s*)?(?:\*\*|__)?[ \t]*"
_HEADER_SUFFIX = r"[ \t]*(?:\*\*|__)?[ \t]*:[ \t]*(?:\*\*|__)?"

_EMPTY_MARKERS = ("none detected", "none", "n/a")
_BULLET_CHARS = "-•*+"
# A11-M7: bound a single flag's length on the METADATA path. `truncate_flag_display`
# bounds the re-injection path only, so an unbounded flag string reached
# `metadata['*_flags']` and `accumulated` at full critique length.
_MAX_FLAG_CHARS = 500

_DECORATION_LEAD_RE = re.compile(r"^(?:[-•*+]\s*)?(?:\d+[.)]\s*)?")
_EMPHASIS_LEAD_RE = re.compile(r"^(?:\*\*|__)+")
_EMPHASIS_TAIL_RE = re.compile(r"(?:\*\*|__)+$")


def _header_anchor_re(header: str) -> re.Pattern[str]:
    """Compile a line-anchored, formatting-tolerant matcher for `header`."""
    core = header.strip().rstrip(":").strip()
    body = r"[ \t]+".join(re.escape(word) for word in core.split())
    return re.compile(rf"(?mi)^{_HEADER_PREFIX}{body}{_HEADER_SUFFIX}")


def _strip_decoration(text: str) -> str:
    """Strip a leading bullet/number and surrounding markdown emphasis."""
    out = _DECORATION_LEAD_RE.sub("", text.strip())
    out = _EMPHASIS_LEAD_RE.sub("", out)
    out = _EMPHASIS_TAIL_RE.sub("", out)
    return out.strip()


def _is_prose_terminator(lower: str) -> bool:
    """True for the two prose lines the templates emit after the flag blocks.

    A11-L4: the previous rule stopped on ANY line beginning `overall`, so a
    genuine flag reading "Overall recall breadth is understated" terminated
    the section and emptied the class (fail-OPEN). All 58 criteria templates
    emit exactly `Overall score:` and `Key issues:`, so the prefix can be
    exact. Callers must only apply this to UN-bulleted lines.
    """
    return lower.startswith(("overall score", "key issues", "#"))


def _is_section_header(lhs: str, rhs: str, seen_bullet: bool) -> bool:
    """True iff `lhs: rhs` is a sibling section header that ends the section.

    A11-L5. An uppercase LHS alone is not sufficient: both of these are
    `UPPERCASE: content` and they mean opposite things —

        RECOMMENDATION: align the local label      <- sibling section
        LOT RANGE: too narrow, extend to 2024-08   <- a flag, written flat

    Treating the second as a header empties the class (fail-OPEN); treating
    the first as a flag merely over-collects (fail-safe). The discriminator is
    `seen_bullet`: every criteria template asks for `[bullet list]`, so once a
    bulleted flag has been seen, the section's idiom is established and a
    following un-bulleted `UPPERCASE:` line is a sibling. Before any bullet
    appears, the reviewer may be writing flat `LABEL: value` flags, so only an
    unambiguous header — one this parser names (`… FLAGS`, `… VETO`) or one
    with no content of its own — terminates.
    """
    if not lhs or not _is_sibling_header_lhs(lhs):
        return False
    if lhs.endswith(("FLAGS", "VETO")):
        return True
    if not rhs or rhs.lower().rstrip(".") in _EMPTY_MARKERS:
        return True
    return seen_bullet


def missing_flag_headers(critique: str, headers: Iterable[str]) -> list[str]:
    """Return the headers that have NO section anywhere in `critique`.

    A11-M1. `extract_flags` returns `[]` both when the reviewer wrote
    `SCOPE FLAGS: None detected` and when it never emitted the header at all.
    The convergence gate `not any(current.values())` cannot tell those apart,
    so a reviewer that silently drops a section satisfies that safety class
    forever — FAIL-OPEN.

    A workflow must treat a missing header as "this class was not assessed"
    and refuse to converge, NOT as "this class is clean".
    """
    return [h for h in headers if _header_anchor_re(h).search(critique) is None]


def extract_flags(critique: str, header: str) -> list[str]:
    """
    Parse a named FLAGS section out of a reviewer critique.

    Returns the list of bullet items under `header`, stopping at the next
    section header. A section header is any of:

    • an un-bulleted line starting `Overall score`, `Key issues`, or `#`
    • a sibling `… FLAGS:` / `… VETO:` line
    • an uppercase `HEADER:` line with no content or an empty marker after it

    Returns `[]` if the header is absent, or if the section's FIRST content
    line is one of the conventional empty markers: `None detected`, `None`,
    `n/a` (case-insensitive, optional trailing period).

    **`[]` is ambiguous** — it means "clean" OR "the reviewer never emitted
    this section". Callers whose convergence gate depends on emptiness MUST
    additionally consult `missing_flag_headers` (A11-M1).

    When the header occurs more than once at line start, the LAST occurrence
    wins (A11-M4): every criteria template says *"End your review with exactly
    these lines"*, so the final block is authoritative. Taking the first match
    let an earlier quoted `SCOPE FLAGS: None detected` — e.g. the reviewer
    echoing caller-supplied text — shadow the real section.

    Used by every flag-gated workflow across all 7 domains; single-flag-class
    callers simply pass their one header.
    """
    matches = list(_header_anchor_re(header).finditer(critique))
    if not matches:
        return []
    section = critique[matches[-1].end():]
    flags: list[str] = []
    seen_bullet = False
    for raw_line in section.splitlines():
        stripped_raw = raw_line.strip()
        if not stripped_raw:
            continue
        is_bullet = stripped_raw[:1] in _BULLET_CHARS
        stripped = _strip_decoration(stripped_raw)
        if not stripped:
            continue
        lower = stripped.lower()
        if not is_bullet and _is_prose_terminator(lower):
            break
        if ":" in stripped:
            lhs, rhs = stripped.split(":", 1)
            if not is_bullet and _is_section_header(lhs.strip(), rhs.strip(), seen_bullet):
                break
        if lower.rstrip(".") in _EMPTY_MARKERS:
            # A11-L3: an empty marker only means "class is empty" when it is
            # the section's FIRST content line. Appearing after real flags it
            # terminates the section rather than discarding what was already
            # collected (the previous `return []` was fail-OPEN).
            if not flags:
                return []
            break
        flags.append(stripped[:_MAX_FLAG_CHARS])
        seen_bullet = seen_bullet or is_bullet
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

    Sibling-header detection uses the shared `_is_section_header` helper
    (H-IND-1 charset via `_is_sibling_header_lhs`, plus the A11-L5 refinement).

    The marker anchor is formatting-tolerant (A11-M5): `**REVIEWER VETO:**`,
    `- REVIEWER VETO:`, `1. REVIEWER VETO:` and `REVIEWER VETO :` all used to
    yield None against a genuine veto — a silently dropped halt directive.

    When the marker occurs more than once at line start the LAST occurrence
    wins (A11-M4). Taking the first let an earlier `REVIEWER VETO: None` —
    e.g. the reviewer quoting the criteria block or echoing caller text —
    suppress a real veto emitted later.

    The returned directive is control-char-stripped and bounded via
    `sanitize_for_prompt` (A11-M8): it is rendered verbatim into the
    operator-facing `WorkflowResult.output` by every veto workflow, so raw
    model text must not carry terminal escapes into that surface.
    """
    matches = list(_header_anchor_re(marker).finditer(critique))
    if not matches:
        return None

    rest = critique[matches[-1].end():]
    # A11-L2: split the marker line off explicitly. The previous form captured
    # it with `(.*)$` and left `rest` starting with "\n", so `splitlines()[0]`
    # was "" and the blank-line rule broke immediately — every continuation
    # line was dropped whenever the marker line carried text, contradicting
    # both the docstring and the inline NOTE.
    newline = rest.find("\n")
    if newline == -1:
        first_line, continuation = rest, ""
    else:
        first_line, continuation = rest[:newline], rest[newline + 1:]

    collected: list[str] = []
    seen_bullet = False
    first_line = _strip_decoration(first_line)
    if first_line and first_line.lower().rstrip(".") not in _EMPTY_MARKERS:
        collected.append(first_line)

    for raw in continuation.splitlines():
        line = raw.strip()
        if not line:
            if collected:
                break
            continue
        is_bullet = line[:1] in _BULLET_CHARS
        line = _strip_decoration(line)
        if not line:
            continue
        lower = line.lower()
        if not is_bullet and _is_prose_terminator(lower):
            break
        if ":" in line:
            lhs, rhs = line.split(":", 1)
            if not is_bullet and _is_section_header(lhs.strip(), rhs.strip(), seen_bullet):
                break
        collected.append(line)
        seen_bullet = seen_bullet or is_bullet

    if not collected:
        return None
    return sanitize_for_prompt(" ".join(collected), max_chars=max_chars)
