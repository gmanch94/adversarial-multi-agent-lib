"""
Config — secret-aware dataclass with validated fields and a redacting repr.

Security properties:
- API keys never appear in repr/str/logs (CRIT-1).
- Empty OpenAI key with OpenAI reviewer raises at construction (MED-8).
- Empty Gemini key with Gemini executor raises at construction.
- Score threshold and round caps are bounds-checked at construction (MED-1).
- ledger_path / wiki_path / skills_dir are resolved to absolute paths under
  an optional base dir (LOW-6).
- EFFORT_LEVEL invalid value error names the env var (LOW-1).
- Same-family executor+reviewer pairing emits UserWarning (echo-chamber risk, D2/D8).
"""
from __future__ import annotations

import os
import warnings
from dataclasses import dataclass, field, fields
from enum import Enum
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from ._internal import redact_secret, safe_resolve_path

load_dotenv()


_SECRET_FIELDS: frozenset[str] = frozenset(
    {"anthropic_api_key", "openai_api_key", "gemini_api_key"}
)


class EffortLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


class ReviewerProvider(str, Enum):
    OPENAI = "openai"
    ANTHROPIC = "anthropic"


class ExecutorProvider(str, Enum):
    ANTHROPIC = "anthropic"
    GEMINI = "gemini"


def _effort_from_env() -> EffortLevel:
    raw = os.getenv("EFFORT_LEVEL", "high")
    try:
        return EffortLevel(raw)
    except ValueError as exc:
        valid = ", ".join(e.value for e in EffortLevel)
        raise ValueError(
            f"EFFORT_LEVEL='{raw}' is not a valid effort level. Use one of: {valid}"
        ) from exc


def _int_from_env(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = os.getenv(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name}='{raw}' is not a valid integer") from exc
    if not (min_value <= value <= max_value):
        raise ValueError(f"{name}={value} out of range [{min_value}, {max_value}]")
    return value


def _float_from_env(name: str, default: float, *, min_value: float, max_value: float) -> float:
    raw = os.getenv(name, str(default))
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError(f"{name}='{raw}' is not a valid number") from exc
    if not (min_value <= value <= max_value):
        raise ValueError(f"{name}={value} out of range [{min_value}, {max_value}]")
    return value


@dataclass
class Config:
    # Executor
    executor_model: str = "claude-opus-4-7"
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    executor_provider: ExecutorProvider = ExecutorProvider.ANTHROPIC

    # Gemini executor (required iff executor_provider=gemini)
    gemini_api_key: str = field(default_factory=lambda: os.getenv("GEMINI_API_KEY", ""))
    gemini_executor_model: str = "gemini-2.5-pro"

    # Reviewer
    reviewer_provider: ReviewerProvider = ReviewerProvider.OPENAI
    reviewer_model: str = "gpt-4o"
    reviewer_anthropic_model: str = "claude-opus-4-7"
    openai_api_key: str = field(default_factory=lambda: os.getenv("OPENAI_API_KEY", ""))

    # Effort
    effort: EffortLevel = field(default_factory=_effort_from_env)

    # Convergence
    max_review_rounds: int = field(
        default_factory=lambda: _int_from_env(
            "MAX_REVIEW_ROUNDS", 5, min_value=1, max_value=50
        )
    )
    score_threshold: float = field(
        default_factory=lambda: _float_from_env(
            "SCORE_THRESHOLD", 8.0, min_value=0.0, max_value=10.0
        )
    )

    # Paths (resolved + sandboxed at __post_init__)
    workspace_dir: str = "."
    wiki_path: str = "wiki.json"
    ledger_path: str = "ledger.json"
    skills_dir: str = "skills"

    # Verifier / editor knobs
    audit_context_chars: int = 4000     # MED-4 — configurable, was hard-coded 2000
    request_timeout_seconds: float = 120.0
    max_claim_text_chars: int = 1000    # HIGH-3 — bound claim text length
    max_wiki_body_chars: int = 8000     # HIGH-2 — bound wiki entry body length

    # ------------------------------------------------------------------
    # Construction-time validation + path sandboxing
    # ------------------------------------------------------------------

    def __post_init__(self) -> None:
        # Anthropic key required for Anthropic executor or Anthropic reviewer
        _needs_anthropic = (
            self.executor_provider == ExecutorProvider.ANTHROPIC
            or self.reviewer_provider == ReviewerProvider.ANTHROPIC
        )
        if _needs_anthropic and not self.anthropic_api_key:
            raise ValueError(
                "ANTHROPIC_API_KEY is unset; set it in .env or pass anthropic_api_key=..."
            )

        # Gemini key required iff executor is Gemini
        if self.executor_provider == ExecutorProvider.GEMINI and not self.gemini_api_key:
            raise ValueError(
                "GEMINI_API_KEY is unset but executor_provider=gemini; "
                "set the key or switch to executor_provider=anthropic"
            )

        # OpenAI key required iff reviewer is OpenAI
        if self.reviewer_provider == ReviewerProvider.OPENAI and not self.openai_api_key:
            raise ValueError(
                "OPENAI_API_KEY is unset but reviewer_provider=openai; "
                "set the key or switch to reviewer_provider=anthropic"
            )

        # Same-family pairing warning — echo-chamber risk per ARIS §3.2, D2/D8
        if (
            self.executor_provider == ExecutorProvider.ANTHROPIC
            and self.reviewer_provider == ReviewerProvider.ANTHROPIC
        ):
            warnings.warn(
                "executor_provider=anthropic and reviewer_provider=anthropic pair "
                "the same model family. Cross-family pairing (e.g., Gemini executor + "
                "OpenAI reviewer) is recommended to prevent echo-chamber effects "
                "(ARIS §3.2). Set EXECUTOR_PROVIDER=gemini or REVIEWER_PROVIDER=openai.",
                UserWarning,
                stacklevel=2,
            )

        # Bounds re-validate (covers programmatic construction, not just env)
        if not (1 <= self.max_review_rounds <= 50):
            raise ValueError(
                f"max_review_rounds={self.max_review_rounds} out of range [1, 50]"
            )
        if not (0.0 <= self.score_threshold <= 10.0):
            raise ValueError(
                f"score_threshold={self.score_threshold} out of range [0.0, 10.0]"
            )

        # Resolve all paths relative to workspace_dir; sandbox them under it
        workspace = safe_resolve_path(self.workspace_dir)
        workspace.mkdir(parents=True, exist_ok=True)
        self.workspace_dir = str(workspace)

        for attr in ("wiki_path", "ledger_path", "skills_dir"):
            raw = getattr(self, attr)
            candidate = Path(raw)
            if not candidate.is_absolute():
                candidate = workspace / candidate
            resolved = safe_resolve_path(candidate, must_be_under=workspace)
            setattr(self, attr, str(resolved))

    # ------------------------------------------------------------------
    # Redacting repr / str / dict — CRIT-1
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        parts: list[str] = []
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in _SECRET_FIELDS:
                rendered = redact_secret(value)
            else:
                rendered = repr(value)
            parts.append(f"{f.name}={rendered}")
        return f"Config({', '.join(parts)})"

    def __str__(self) -> str:
        return self.__repr__()

    def safe_dict(self) -> dict[str, Any]:
        """Return a copy of the config with secrets redacted. Safe to log."""
        out: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if f.name in _SECRET_FIELDS:
                out[f.name] = redact_secret(value)
            elif isinstance(value, Enum):
                out[f.name] = value.value
            else:
                out[f.name] = value
        return out

    def use_openai_reviewer(self) -> bool:
        return self.reviewer_provider == ReviewerProvider.OPENAI

    def use_gemini_executor(self) -> bool:
        return self.executor_provider == ExecutorProvider.GEMINI

    @classmethod
    def from_env(cls) -> "Config":
        provider_str = os.getenv("REVIEWER_PROVIDER", "openai").lower()
        try:
            provider = ReviewerProvider(provider_str)
        except ValueError:
            provider = ReviewerProvider.OPENAI

        exec_str = os.getenv("EXECUTOR_PROVIDER", "anthropic").lower()
        try:
            exec_provider = ExecutorProvider(exec_str)
        except ValueError:
            exec_provider = ExecutorProvider.ANTHROPIC

        return cls(reviewer_provider=provider, executor_provider=exec_provider)
