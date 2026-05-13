"""
ResearchWiki — persistent knowledge store shared across workflow runs.

Security properties:
- Atomic writes (HIGH-4).
- Body text bounded + sanitized before persistence (HIGH-2, MED-3).
- `context_for_round()` filters by round number (LOW-4), wraps every entry in
  fenced delimiters so persisted text cannot escape the prompt structure
  (HIGH-2), and enforces a total-character budget (MED-3).
- Resilient `from_dict` (MED-2).
- Longer IDs (LOW-3).
"""
from __future__ import annotations

import json
import uuid
import warnings
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ._internal import atomic_write_text, is_safe_id, sanitize_for_prompt


_DEFAULT_MAX_BODY_CHARS = 8000


class EntryKind(str, Enum):
    LITERATURE = "literature"
    HYPOTHESIS = "hypothesis"
    EXPERIMENT = "experiment"
    FEEDBACK = "feedback"
    IMPROVEMENT = "improvement"
    NOTE = "note"


@dataclass
class WikiEntry:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    kind: EntryKind = EntryKind.NOTE
    title: str = ""
    body: str = ""
    tags: list[str] = field(default_factory=list)
    round_num: int = 0
    supersedes: Optional[str] = None
    approved: Optional[bool] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_by: Optional[str] = None      # M1: audit trail for human approval
    approved_at: Optional[str] = None      # M1: ISO timestamp of approval

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["kind"] = self.kind.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WikiEntry":
        """Resilient loader: ignores unknown keys, fills missing with defaults."""
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in d.items() if k in known}
        # H5: refuse attacker-controlled ids; regenerate on invalid charset.
        if "id" in filtered and not is_safe_id(filtered["id"]):
            filtered["id"] = uuid.uuid4().hex[:12]
        # L2: refuse non-ISO timestamps from disk. An attacker with write
        # access cannot forge audit timestamps that pass downstream parsers.
        for ts_field in ("created_at", "approved_at"):
            if ts_field in filtered and filtered[ts_field] is not None:
                try:
                    datetime.fromisoformat(str(filtered[ts_field]))
                except (TypeError, ValueError):
                    filtered[ts_field] = (
                        datetime.now(timezone.utc).isoformat()
                        if ts_field == "created_at"
                        else None
                    )
        if "kind" in filtered:
            try:
                filtered["kind"] = EntryKind(filtered["kind"])
            except ValueError:
                filtered["kind"] = EntryKind.NOTE
        raw_tags = filtered.get("tags", [])
        filtered["tags"] = [str(t) for t in raw_tags] if isinstance(raw_tags, list) else []
        return cls(**filtered)


class ResearchWiki:
    """
    Shared persistent knowledge store.
    """

    def __init__(
        self,
        path: str = "wiki.json",
        *,
        max_body_chars: int = _DEFAULT_MAX_BODY_CHARS,
    ) -> None:
        self._path = Path(path)
        self._max_body_chars = max_body_chars
        self._entries: dict[str, WikiEntry] = {}
        self._load()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add(
        self,
        kind: EntryKind,
        title: str,
        body: str,
        tags: list[str] | None = None,
        round_num: int = 0,
        supersedes: str | None = None,
    ) -> str:
        title = self._bound(title, 500, "title")
        body = self._bound(body, self._max_body_chars, "body")
        # H1: strip control chars on write so persisted bodies cannot smuggle
        # them into any later read path (not just context_for_round). Caller
        # is the chokepoint; downstream workflows that read wiki entries
        # verbatim now see sanitized content.
        title = sanitize_for_prompt(title, max_chars=500)
        body = sanitize_for_prompt(body, max_chars=self._max_body_chars)
        if supersedes is not None and supersedes not in self._entries:
            raise ValueError(f"supersedes references unknown entry: {supersedes}")
        entry = WikiEntry(
            kind=kind,
            title=title,
            body=body,
            tags=[str(t) for t in (tags or [])],
            round_num=int(round_num),
            supersedes=supersedes,
        )
        while entry.id in self._entries:
            entry.id = uuid.uuid4().hex[:12]
        self._entries[entry.id] = entry
        self._save()
        return entry.id

    def add_feedback(self, critique: str, round_num: int, score: float) -> str:
        return self.add(
            EntryKind.FEEDBACK,
            title=f"Round {round_num} review (score={score:.1f})",
            body=critique,
            round_num=round_num,
        )

    def add_improvement(self, proposal: str, round_num: int) -> str:
        return self.add(
            EntryKind.IMPROVEMENT,
            title=f"Improvement proposal (round {round_num})",
            body=proposal,
            round_num=round_num,
        )

    def approve_improvement(self, entry_id: str, human_reviewer_id: str) -> None:
        """
        Approve a self-improvement proposal. CRIT-2 / M1: requires a
        non-empty human_reviewer_id which is persisted as audit trail.
        Workflow code that calls this is the caller-of-record. The class
        does not enforce a token or capability — the audit field is the
        forensic trail that lets you grep history for who approved what.
        """
        if not isinstance(human_reviewer_id, str) or not human_reviewer_id.strip():
            raise ValueError(
                "approve_improvement requires a non-empty human_reviewer_id "
                "(this is an audit-trail field — name the human approving the change)"
            )
        entry = self._must_get(entry_id)
        if entry.kind != EntryKind.IMPROVEMENT:
            raise ValueError(f"Entry {entry_id} is not an improvement proposal")
        entry.approved = True
        entry.approved_by = human_reviewer_id.strip()
        entry.approved_at = datetime.now(timezone.utc).isoformat()
        self._save()

    def reject_improvement(self, entry_id: str, human_reviewer_id: str) -> None:
        if not isinstance(human_reviewer_id, str) or not human_reviewer_id.strip():
            raise ValueError(
                "reject_improvement requires a non-empty human_reviewer_id"
            )
        entry = self._must_get(entry_id)
        if entry.kind != EntryKind.IMPROVEMENT:
            raise ValueError(f"Entry {entry_id} is not an improvement proposal")
        entry.approved = False
        entry.approved_by = human_reviewer_id.strip()
        entry.approved_at = datetime.now(timezone.utc).isoformat()
        self._save()

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, entry_id: str) -> WikiEntry:
        return self._must_get(entry_id)

    def by_kind(self, kind: EntryKind) -> list[WikiEntry]:
        return [e for e in self._entries.values() if e.kind == kind]

    def by_tag(self, tag: str) -> list[WikiEntry]:
        return [e for e in self._entries.values() if tag in e.tags]

    def by_round(self, round_num: int) -> list[WikiEntry]:
        return [e for e in self._entries.values() if e.round_num == round_num]

    def pending_improvements(self) -> list[WikiEntry]:
        return [
            e for e in self._entries.values()
            if e.kind == EntryKind.IMPROVEMENT and e.approved is None
        ]

    def approved_improvements(self) -> list[WikiEntry]:
        return [
            e for e in self._entries.values()
            if e.kind == EntryKind.IMPROVEMENT and e.approved is True
        ]

    def context_for_round(
        self,
        round_num: int,
        max_entries: int = 20,
        max_total_chars: int = 6000,
        per_entry_chars: int = 400,
    ) -> str:
        """
        Return a fenced, sanitized summary of wiki entries with `round_num <=` arg.

        Each entry is wrapped in `<<WIKI_ENTRY>> ... <<END_WIKI_ENTRY>>` delimiters
        and sanitized to strip control characters before injection. The total
        character budget is enforced. Improvement proposals are NEVER included
        (an attacker who got an improvement into the wiki must not have it
        replayed into every subsequent executor prompt — HIGH-2).
        """
        eligible = [
            e for e in self._entries.values()
            if e.round_num <= int(round_num) and e.kind != EntryKind.IMPROVEMENT
        ]
        eligible.sort(key=lambda e: e.round_num, reverse=True)
        eligible = eligible[:max_entries]

        chunks: list[str] = []
        total = 0
        for e in eligible:
            kind = e.kind.value.upper()
            title = sanitize_for_prompt(e.title, max_chars=200)
            body = sanitize_for_prompt(e.body, max_chars=per_entry_chars)
            chunk = (
                f"<<WIKI_ENTRY kind={kind} round={e.round_num}>>\n"
                f"title: {title}\n"
                f"body: {body}\n"
                f"<<END_WIKI_ENTRY>>"
            )
            if total + len(chunk) > max_total_chars:
                break
            chunks.append(chunk)
            total += len(chunk)
        return "\n".join(chunks)

    def all(self) -> list[WikiEntry]:
        return list(self._entries.values())

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "entries": {eid: e.to_dict() for eid, e in self._entries.items()},
        }
        atomic_write_text(self._path, json.dumps(data, indent=2))

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw_text = self._path.read_text(encoding="utf-8")
            if not raw_text.strip():
                return
            data = json.loads(raw_text)
        except (OSError, json.JSONDecodeError) as exc:
            # M4: warn instead of silent-skip so corruption/tampering is visible.
            warnings.warn(
                f"ResearchWiki load failed for {self._path}: {exc!r}; "
                f"starting fresh",
                UserWarning,
                stacklevel=2,
            )
            return
        entries_dict = data.get("entries", {}) if isinstance(data, dict) else {}
        if not isinstance(entries_dict, dict):
            return
        for eid, raw in entries_dict.items():
            if not isinstance(raw, dict):
                continue
            try:
                self._entries[str(eid)] = WikiEntry.from_dict(raw)
            except (TypeError, ValueError):
                continue

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _must_get(self, entry_id: str) -> WikiEntry:
        if entry_id not in self._entries:
            raise KeyError(f"unknown entry id: {entry_id}")
        return self._entries[entry_id]

    @staticmethod
    def _bound(value: str, max_chars: int, label: str) -> str:
        if not isinstance(value, str):
            value = str(value)
        if len(value) > max_chars:
            raise ValueError(
                f"wiki {label} length {len(value)} exceeds max {max_chars} chars"
            )
        return value
