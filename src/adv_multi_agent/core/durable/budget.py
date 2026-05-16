"""BudgetTracker — per-run token + USD accumulation with hard caps.

Price table is a static dict for POC; production swaps in a refresh mechanism.
Unknown models warn + count as zero USD (tokens still tracked).
"""
from __future__ import annotations

import warnings
from dataclasses import dataclass
from typing import Any

from .protocols import BudgetExceeded

# Per-1M-token prices (USD). POC values; refresh from vendor pricing pages.
_PRICE_TABLE: dict[str, tuple[float, float]] = {
    "claude-opus-4-7": (15.0, 75.0),
    "claude-opus-4-8": (15.0, 75.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.60),
    "gemini-2.5-pro": (1.25, 5.0),
}


def estimate_usd(model: str, tokens_in: int, tokens_out: int) -> float:
    if model not in _PRICE_TABLE:
        warnings.warn(
            f"no price table entry for model={model!r}; counting as $0.00",
            UserWarning,
            stacklevel=2,
        )
        return 0.0
    p_in, p_out = _PRICE_TABLE[model]
    return round((tokens_in / 1_000_000) * p_in + (tokens_out / 1_000_000) * p_out, 4)


@dataclass(frozen=True)
class BudgetSnapshot:
    tokens_in: int
    tokens_out: int
    usd_spent: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "tokens_in": self.tokens_in,
            "tokens_out": self.tokens_out,
            "usd_spent": self.usd_spent,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BudgetSnapshot":
        return cls(
            tokens_in=int(d["tokens_in"]),
            tokens_out=int(d["tokens_out"]),
            usd_spent=float(d["usd_spent"]),
        )


class BudgetTracker:
    def __init__(
        self,
        max_tokens_in: int | None = None,
        max_tokens_out: int | None = None,
        max_usd: float | None = None,
    ) -> None:
        if max_tokens_in is None and max_tokens_out is None and max_usd is None:
            warnings.warn(
                "BudgetTracker constructed with no caps; long-running spend is unbounded. "
                "Set max_tokens_in / max_tokens_out / max_usd for fail-loud-by-default.",
                UserWarning,
                stacklevel=2,
            )
        self._max_tokens_in = max_tokens_in
        self._max_tokens_out = max_tokens_out
        self._max_usd = max_usd
        self._tokens_in = 0
        self._tokens_out = 0
        self._usd_spent = 0.0

    @classmethod
    def from_snapshot(
        cls,
        snap: BudgetSnapshot,
        *,
        max_tokens_in: int | None = None,
        max_tokens_out: int | None = None,
        max_usd: float | None = None,
    ) -> "BudgetTracker":
        t = cls(max_tokens_in=max_tokens_in, max_tokens_out=max_tokens_out, max_usd=max_usd)
        t._tokens_in = snap.tokens_in
        t._tokens_out = snap.tokens_out
        t._usd_spent = snap.usd_spent
        return t

    def record(self, model: str, tokens_in: int, tokens_out: int) -> None:
        new_in = self._tokens_in + tokens_in
        new_out = self._tokens_out + tokens_out
        new_usd = round(self._usd_spent + estimate_usd(model, tokens_in, tokens_out), 4)
        if self._max_tokens_in is not None and new_in > self._max_tokens_in:
            raise BudgetExceeded(
                f"tokens_in cap exceeded: would be {new_in} > {self._max_tokens_in}"
            )
        if self._max_tokens_out is not None and new_out > self._max_tokens_out:
            raise BudgetExceeded(
                f"tokens_out cap exceeded: would be {new_out} > {self._max_tokens_out}"
            )
        if self._max_usd is not None and new_usd > self._max_usd:
            raise BudgetExceeded(
                f"usd cap exceeded: would be ${new_usd:.4f} > ${self._max_usd:.4f}"
            )
        self._tokens_in = new_in
        self._tokens_out = new_out
        self._usd_spent = new_usd

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot(
            tokens_in=self._tokens_in,
            tokens_out=self._tokens_out,
            usd_spent=self._usd_spent,
        )
