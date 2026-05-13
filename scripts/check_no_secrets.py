"""
L7: pre-commit / CI guard against accidentally committed API keys.

Scans the working tree for tokens that match known key prefixes.
Returns exit code 1 if any match is found outside of .env.example
(the only file allowed to contain literal `sk-ant-` / `sk-` shapes
as placeholders).

Run:
    python scripts/check_no_secrets.py

Wire into CI or pre-commit:
    - id: check-no-secrets
      entry: python scripts/check_no_secrets.py
      language: system
      pass_filenames: false
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# Heuristic patterns. False positives are recoverable (operator edits the
# file or adds to ALLOWLIST_PATHS). False negatives ship to production.
PATTERNS: dict[str, re.Pattern[str]] = {
    "anthropic_key": re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}"),
    "openai_key": re.compile(r"sk-[A-Za-z0-9]{32,}"),
    "openai_proj_key": re.compile(r"sk-proj-[A-Za-z0-9_-]{20,}"),
    "google_api_key": re.compile(r"AIza[0-9A-Za-z_-]{35}"),
    "github_pat": re.compile(r"ghp_[A-Za-z0-9]{36}"),
}

ALLOWLIST_PATHS = {
    ".env.example",
    "scripts/check_no_secrets.py",
}

# Files matching these patterns are assumed gitignored and not in CI.
SKIP_FILE_PATTERNS = re.compile(r"^\.env(\..+)?$|^\.env\.local$|\.log$")

SKIP_DIRS = {".git", ".venv", "venv", "__pycache__", "dist", "build",
             ".mypy_cache", ".ruff_cache", "node_modules"}


def scan(root: Path) -> int:
    findings: list[tuple[Path, str, int, str]] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        rel = path.relative_to(root).as_posix()
        if rel in ALLOWLIST_PATHS:
            continue
        if SKIP_FILE_PATTERNS.match(path.name):
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for name, regex in PATTERNS.items():
            for match in regex.finditer(text):
                line_no = text.count("\n", 0, match.start()) + 1
                findings.append((path, name, line_no, match.group(0)[:12] + "..."))
    if findings:
        print("Secrets check FAILED:", file=sys.stderr)
        for path, name, line_no, preview in findings:
            print(f"  {path}:{line_no}  [{name}]  {preview}", file=sys.stderr)
        return 1
    print(f"Secrets check OK ({len(PATTERNS)} patterns, scanned from {root})")
    return 0


if __name__ == "__main__":
    sys.exit(scan(Path.cwd()))
