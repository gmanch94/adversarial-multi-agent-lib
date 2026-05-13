"""Unit tests for Config — provider routing, key validation, same-family warning."""
from __future__ import annotations

import warnings

import pytest

from adv_multi_agent.core.config import (
    Config,
    EffortLevel,
    ExecutorProvider,
    ReviewerProvider,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _anthropic_openai(**kwargs: object) -> Config:
    """Minimal valid config: Anthropic executor + OpenAI reviewer."""
    return Config(
        anthropic_api_key="test-ant",
        openai_api_key="test-oai",
        workspace_dir=".",
        **kwargs,  # type: ignore[arg-type]
    )


def _gemini_openai(**kwargs: object) -> Config:
    """Minimal valid config: Gemini executor + OpenAI reviewer."""
    return Config(
        anthropic_api_key="",
        gemini_api_key="test-gem",
        openai_api_key="test-oai",
        executor_provider=ExecutorProvider.GEMINI,
        workspace_dir=".",
        **kwargs,  # type: ignore[arg-type]
    )


# ---------------------------------------------------------------------------
# ExecutorProvider routing
# ---------------------------------------------------------------------------


class TestExecutorProvider:
    def test_default_is_anthropic(self) -> None:
        cfg = _anthropic_openai()
        assert cfg.executor_provider == ExecutorProvider.ANTHROPIC

    def test_gemini_provider_accepted(self) -> None:
        cfg = _gemini_openai()
        assert cfg.executor_provider == ExecutorProvider.GEMINI
        assert cfg.use_gemini_executor() is True

    def test_anthropic_provider_use_gemini_false(self) -> None:
        cfg = _anthropic_openai()
        assert cfg.use_gemini_executor() is False

    def test_gemini_executor_model_default(self) -> None:
        cfg = _gemini_openai()
        assert cfg.gemini_executor_model == "gemini-2.5-pro"

    def test_gemini_executor_model_override(self) -> None:
        cfg = _gemini_openai(gemini_executor_model="gemini-2.5-flash")
        assert cfg.gemini_executor_model == "gemini-2.5-flash"


# ---------------------------------------------------------------------------
# Key validation
# ---------------------------------------------------------------------------


class TestKeyValidation:
    def test_gemini_key_required_when_gemini_executor(self) -> None:
        with pytest.raises(ValueError, match="GEMINI_API_KEY"):
            Config(
                anthropic_api_key="",
                gemini_api_key="",
                openai_api_key="test-oai",
                executor_provider=ExecutorProvider.GEMINI,
                workspace_dir=".",
            )

    def test_anthropic_key_not_required_for_gemini_plus_openai(self) -> None:
        # Gemini executor + OpenAI reviewer: no Anthropic key needed
        cfg = Config(
            anthropic_api_key="",
            gemini_api_key="test-gem",
            openai_api_key="test-oai",
            executor_provider=ExecutorProvider.GEMINI,
            workspace_dir=".",
        )
        assert cfg.executor_provider == ExecutorProvider.GEMINI

    def test_anthropic_key_required_for_anthropic_reviewer(self) -> None:
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            Config(
                anthropic_api_key="",
                gemini_api_key="test-gem",
                openai_api_key="",
                executor_provider=ExecutorProvider.GEMINI,
                reviewer_provider=ReviewerProvider.ANTHROPIC,
                workspace_dir=".",
            )

    def test_openai_key_required_when_openai_reviewer(self) -> None:
        with pytest.raises(ValueError, match="OPENAI_API_KEY"):
            Config(
                anthropic_api_key="test-ant",
                openai_api_key="",
                reviewer_provider=ReviewerProvider.OPENAI,
                workspace_dir=".",
            )


# ---------------------------------------------------------------------------
# Same-family warning
# ---------------------------------------------------------------------------


class TestSameFamilyWarning:
    def test_anthropic_executor_anthropic_reviewer_warns(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            Config(
                anthropic_api_key="test-ant",
                openai_api_key="",
                reviewer_provider=ReviewerProvider.ANTHROPIC,
                workspace_dir=".",
            )
        user_warns = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warns) == 1
        assert "echo-chamber" in str(user_warns[0].message).lower()

    def test_anthropic_executor_openai_reviewer_no_warn(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _anthropic_openai()
        user_warns = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warns) == 0

    def test_gemini_executor_anthropic_reviewer_no_warn(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            Config(
                anthropic_api_key="test-ant",
                gemini_api_key="test-gem",
                openai_api_key="",
                executor_provider=ExecutorProvider.GEMINI,
                reviewer_provider=ReviewerProvider.ANTHROPIC,
                workspace_dir=".",
            )
        user_warns = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warns) == 0

    def test_gemini_executor_openai_reviewer_no_warn(self) -> None:
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            _gemini_openai()
        user_warns = [w for w in caught if issubclass(w.category, UserWarning)]
        assert len(user_warns) == 0


# ---------------------------------------------------------------------------
# from_env
# ---------------------------------------------------------------------------


class TestFromEnv:
    def test_from_env_parses_executor_provider(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTOR_PROVIDER", "gemini")
        monkeypatch.setenv("GEMINI_API_KEY", "test-gem")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "")
        monkeypatch.setenv("OPENAI_API_KEY", "test-oai")
        cfg = Config.from_env()
        assert cfg.executor_provider == ExecutorProvider.GEMINI

    def test_from_env_defaults_anthropic(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("EXECUTOR_PROVIDER", "")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
        monkeypatch.setenv("OPENAI_API_KEY", "test-oai")
        cfg = Config.from_env()
        assert cfg.executor_provider == ExecutorProvider.ANTHROPIC

    def test_from_env_invalid_executor_provider_falls_back(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setenv("EXECUTOR_PROVIDER", "bedrock")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "test-ant")
        monkeypatch.setenv("OPENAI_API_KEY", "test-oai")
        cfg = Config.from_env()
        assert cfg.executor_provider == ExecutorProvider.ANTHROPIC
