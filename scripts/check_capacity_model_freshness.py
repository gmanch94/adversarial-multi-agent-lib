"""Tier 2.5 / D-COST-6 — CI freshness check for docs/capacity-model.md.

Parses the `Last refreshed: YYYY-MM-DD` header stamp. Emits:
  WARN at 90 days since refresh (exit 0; surfaces in CI output)
  FAIL at 180 days since refresh (exit 1; fails the docs-only workflow run)

Not a code-merge gate — the freshness check lives in the docs-only path so a
warning persists across PRs as a nudge.

Usage:
    python scripts/check_capacity_model_freshness.py
"""
from __future__ import annotations

import datetime as _dt
import pathlib
import re
import sys


_DOC_PATH = pathlib.Path("docs/capacity-model.md")
_STAMP_RE = re.compile(r"^\*\*Last refreshed:\*\*\s+(\d{4}-\d{2}-\d{2})\s*$", re.MULTILINE)
_WARN_DAYS = 90
_FAIL_DAYS = 180


def _read_stamp(path: pathlib.Path) -> _dt.date | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    m = _STAMP_RE.search(text)
    if not m:
        return None
    try:
        return _dt.date.fromisoformat(m.group(1))
    except ValueError:
        return None


def main() -> int:
    stamp = _read_stamp(_DOC_PATH)
    if stamp is None:
        print(f"FAIL: could not parse 'Last refreshed: YYYY-MM-DD' from {_DOC_PATH}",
              file=sys.stderr)
        return 1
    today = _dt.date.today()
    age_days = (today - stamp).days
    if age_days < 0:
        print(f"WARN: capacity-model 'Last refreshed' is in the future "
              f"({stamp}, today {today}). Fix the stamp.", file=sys.stderr)
        return 0
    if age_days >= _FAIL_DAYS:
        print(f"FAIL: capacity-model is {age_days}d stale (>= {_FAIL_DAYS}d). "
              f"Refresh per D-COST-6: review assumptions in §2, update SKU "
              f"prices, bump 'Last refreshed' + 'Next review due' stamps.",
              file=sys.stderr)
        return 1
    if age_days >= _WARN_DAYS:
        print(f"WARN: capacity-model is {age_days}d stale (>= {_WARN_DAYS}d). "
              f"Refresh recommended per D-COST-6.")
        return 0
    print(f"OK: capacity-model refreshed {age_days}d ago (last={stamp}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
