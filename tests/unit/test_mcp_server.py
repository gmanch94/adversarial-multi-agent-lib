"""
Smoke tests for adv_multi_agent.skills.mcp_server.

Skips automatically when the `mcp` package is not installed.
All tests are synchronous — they call the tool functions directly,
bypassing the stdio transport layer.
"""
from __future__ import annotations

import json

import pytest

mcp_mod = pytest.importorskip(
    "adv_multi_agent.skills.mcp_server",
    reason="mcp package not installed; skipping MCP server tests",
)


@pytest.fixture(autouse=True)
def reset_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Reset the lazy registry singleton between tests."""
    monkeypatch.setattr(mcp_mod, "_registry", None)


# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------

def test_list_skills_returns_nonempty_list() -> None:
    result = mcp_mod.list_skills()
    assert isinstance(result, list)
    assert len(result) > 0


def test_list_skills_sorted() -> None:
    result = mcp_mod.list_skills()
    assert result == sorted(result)


def test_list_skills_contains_bundled_names() -> None:
    result = mcp_mod.list_skills()
    # A sample of names bundled with the package
    for expected in ("review", "generate", "hypothesis", "literature_review"):
        assert expected in result, f"Expected '{expected}' in list_skills()"


# ---------------------------------------------------------------------------
# describe_skills
# ---------------------------------------------------------------------------

def test_describe_skills_returns_string() -> None:
    result = mcp_mod.describe_skills()
    assert isinstance(result, str)
    assert len(result) > 0


def test_describe_skills_mentions_count() -> None:
    result = mcp_mod.describe_skills()
    assert "Available skills" in result


# ---------------------------------------------------------------------------
# get_skill
# ---------------------------------------------------------------------------

def test_get_skill_returns_json() -> None:
    result = mcp_mod.get_skill("review")
    data = json.loads(result)
    assert data["name"] == "review"
    assert "description" in data
    assert "inputs" in data
    assert "template" in data


def test_get_skill_inputs_is_list() -> None:
    result = mcp_mod.get_skill("review")
    data = json.loads(result)
    assert isinstance(data["inputs"], list)


def test_get_skill_unknown_name_returns_error() -> None:
    result = mcp_mod.get_skill("nonexistent_skill_xyz")
    assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# render_skill
# ---------------------------------------------------------------------------

def test_render_skill_produces_non_empty_output() -> None:
    # 'review' skill requires 'content' and 'criteria' inputs
    skill_data = json.loads(mcp_mod.get_skill("review"))
    inputs = {k: f"sample_{k}" for k in skill_data["inputs"]}
    result = mcp_mod.render_skill("review", inputs)
    assert isinstance(result, str)
    assert len(result) > 0
    assert not result.startswith("Error:")


def test_render_skill_missing_inputs_returns_error() -> None:
    result = mcp_mod.render_skill("review", {})
    assert result.startswith("Error:")


def test_render_skill_unknown_skill_returns_error() -> None:
    result = mcp_mod.render_skill("nonexistent_skill_xyz", {})
    assert result.startswith("Error:")


# ---------------------------------------------------------------------------
# tool count (integration: server exposes exactly 4 tools)
# ---------------------------------------------------------------------------

def test_server_has_four_tools() -> None:
    tools = mcp_mod.mcp._tool_manager.list_tools()
    assert len(tools) == 4
    names = {t.name for t in tools}
    assert names == {"list_skills", "describe_skills", "get_skill", "render_skill"}
