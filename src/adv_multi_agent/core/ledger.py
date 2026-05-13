"""
Claim ledger — tracks every factual claim made by the executor with evidence pointers.

Security properties:
- Atomic file writes via temp+rename (HIGH-4).
- Bounded claim text (HIGH-3) — refuses oversized strings.
- Resilient `from_dict` (MED-2) — extra/missing keys do not crash load.
- Longer IDs (LOW-3) — 12 hex chars, ~7e13 space.
- `resolve()` rejects PENDING as a target (no un-resolving).
"""
from __future__ import annotations

import json
import uuid
from dataclasses import dataclass, field, asdict, fields
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from ._internal import atomic_write_text


_DEFAULT_MAX_CLAIM_CHARS = 2000
_DEFAULT_MAX_EVIDENCE_CHARS = 4000


class ClaimStatus(str, Enum):
    PENDING = "pending"
    SUPPORTED = "supported"
    DISPUTED = "disputed"
    RETRACTED = "retracted"


@dataclass
class Evidence:
    source: str
    excerpt: str
    page_or_line: str = ""


@dataclass
class Claim:
    id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    text: str = ""
    status: ClaimStatus = ClaimStatus.PENDING
    evidence: list[Evidence] = field(default_factory=list)
    round_added: int = 0
    round_resolved: Optional[int] = None
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Claim":
        """Resilient loader: ignores unknown keys, fills missing with defaults."""
        known = {f.name for f in fields(cls)}
        filtered = {k: v for k, v in d.items() if k in known}
        # Coerce status string back to enum
        if "status" in filtered:
            try:
                filtered["status"] = ClaimStatus(filtered["status"])
            except ValueError:
                filtered["status"] = ClaimStatus.PENDING
        # Coerce evidence list back to Evidence dataclasses
        raw_ev = filtered.get("evidence", [])
        ev_list: list[Evidence] = []
        if isinstance(raw_ev, list):
            for item in raw_ev:
                if isinstance(item, dict):
                    ev_list.append(
                        Evidence(
                            source=str(item.get("source", "")),
                            excerpt=str(item.get("excerpt", "")),
                            page_or_line=str(item.get("page_or_line", "")),
                        )
                    )
        filtered["evidence"] = ev_list
        return cls(**filtered)


class ClaimLedger:
    """
    Append-only claim store. Persisted atomically after each mutation.
    """

    def __init__(
        self,
        path: str = "ledger.json",
        *,
        max_claim_chars: int = _DEFAULT_MAX_CLAIM_CHARS,
        max_evidence_chars: int = _DEFAULT_MAX_EVIDENCE_CHARS,
    ) -> None:
        self._path = Path(path)
        self._max_claim_chars = max_claim_chars
        self._max_evidence_chars = max_evidence_chars
        self._claims: dict[str, Claim] = {}
        self._load()

    # ------------------------------------------------------------------
    # Mutations
    # ------------------------------------------------------------------

    def add(self, text: str, round_num: int = 0, notes: str = "") -> str:
        text = self._bound(text, self._max_claim_chars, "claim text")
        notes = self._bound(notes, self._max_claim_chars, "claim notes")
        claim = Claim(text=text, round_added=int(round_num), notes=notes)
        # Resolve any (astronomically unlikely) ID collision
        while claim.id in self._claims:
            claim.id = uuid.uuid4().hex[:12]
        self._claims[claim.id] = claim
        self._save()
        return claim.id

    def attach_evidence(self, claim_id: str, evidence: Evidence) -> None:
        if claim_id not in self._claims:
            raise KeyError(f"unknown claim id: {claim_id}")
        bounded = Evidence(
            source=self._bound(evidence.source, 500, "evidence source"),
            excerpt=self._bound(evidence.excerpt, self._max_evidence_chars, "evidence excerpt"),
            page_or_line=self._bound(evidence.page_or_line, 100, "evidence page_or_line"),
        )
        self._claims[claim_id].evidence.append(bounded)
        self._save()

    def resolve(
        self,
        claim_id: str,
        status: ClaimStatus,
        round_num: int,
        notes: str = "",
    ) -> None:
        if status == ClaimStatus.PENDING:
            raise ValueError("Cannot resolve a claim back to PENDING; use add() for new claims")
        if claim_id not in self._claims:
            raise KeyError(f"unknown claim id: {claim_id}")
        claim = self._claims[claim_id]
        claim.status = status
        claim.round_resolved = int(round_num)
        if notes:
            claim.notes = self._bound(notes, self._max_claim_chars, "claim notes")
        self._save()

    def dispute(self, claim_id: str, round_num: int, critique: str) -> None:
        self.resolve(claim_id, ClaimStatus.DISPUTED, round_num, critique)

    def retract(self, claim_id: str, round_num: int, reason: str = "") -> None:
        self.resolve(claim_id, ClaimStatus.RETRACTED, round_num, reason)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get(self, claim_id: str) -> Claim:
        if claim_id not in self._claims:
            raise KeyError(f"unknown claim id: {claim_id}")
        return self._claims[claim_id]

    def all(self) -> list[Claim]:
        return list(self._claims.values())

    def by_status(self, status: ClaimStatus) -> list[Claim]:
        return [c for c in self._claims.values() if c.status == status]

    def pending(self) -> list[Claim]:
        return self.by_status(ClaimStatus.PENDING)

    def disputed(self) -> list[Claim]:
        return self.by_status(ClaimStatus.DISPUTED)

    def summary(self) -> dict[str, int]:
        counts: dict[str, int] = {s.value: 0 for s in ClaimStatus}
        for c in self._claims.values():
            counts[c.status.value] += 1
        counts["total"] = len(self._claims)
        return counts

    # ------------------------------------------------------------------
    # Persistence
    # ------------------------------------------------------------------

    def _save(self) -> None:
        data = {
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "claims": {cid: c.to_dict() for cid, c in self._claims.items()},
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
        except (OSError, json.JSONDecodeError):
            # Corrupt or unreadable file — start fresh; do not crash the workflow.
            return
        claims_dict = data.get("claims", {}) if isinstance(data, dict) else {}
        if not isinstance(claims_dict, dict):
            return
        for cid, raw in claims_dict.items():
            if not isinstance(raw, dict):
                continue
            try:
                self._claims[str(cid)] = Claim.from_dict(raw)
            except (TypeError, ValueError):
                continue

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _bound(value: str, max_chars: int, label: str) -> str:
        if not isinstance(value, str):
            value = str(value)
        if len(value) > max_chars:
            raise ValueError(
                f"{label} length {len(value)} exceeds max {max_chars} chars"
            )
        return value
