"""
MCP server for SkillRegistry — exposes bundled research skills as MCP tools.

Tools
-----
list_skills      — list all available skill names
describe_skills  — one-line description per skill
get_skill        — full details: description, required inputs, raw template
render_skill     — fill a skill template with caller-supplied inputs

Run (stdio, for use with Claude Code):
    python -m adv_multi_agent.core.skills.mcp_server

Custom skills directory:
    SKILLS_DIR=/path/to/skills python -m adv_multi_agent.core.skills.mcp_server

Custom domain (research or parole):
    SKILLS_DOMAIN=parole python -m adv_multi_agent.core.skills.mcp_server

Register with Claude Code:
    claude mcp add adv-multi-agent-skills -- python -m adv_multi_agent.core.skills.mcp_server
"""
from __future__ import annotations

import json
import os

try:
    from mcp.server.fastmcp import FastMCP
except ImportError as exc:
    raise ImportError(
        "mcp package required for the MCP server. "
        "Install with: pip install 'adv-multi-agent[mcp]'"
    ) from exc

from adv_multi_agent.core.skills.registry import SkillRegistry

# ---------------------------------------------------------------------------
# Registry (lazy singleton — loaded on first tool call)
# ---------------------------------------------------------------------------

_registry: SkillRegistry | None = None


def _get_registry() -> SkillRegistry:
    global _registry
    if _registry is None:
        skills_dir = os.getenv("SKILLS_DIR", "")
        if skills_dir:
            _registry = SkillRegistry(skills_dir)
        else:
            domain = os.getenv("SKILLS_DOMAIN", "research")
            _registry = SkillRegistry(str(SkillRegistry.bundled_skills_path(domain)))
    return _registry


# ---------------------------------------------------------------------------
# Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "adv-multi-agent-skills",
    instructions=(
        "Research skill library for adversarial multi-agent pipelines. "
        "Call list_skills to discover what's available, get_skill to inspect a skill's "
        "required inputs, then render_skill to produce a filled prompt."
    ),
)


@mcp.tool()
def list_skills() -> list[str]:
    """List all available skill names."""
    return _get_registry().list()


@mcp.tool()
def describe_skills() -> str:
    """Return a formatted summary of every skill: name and one-line description."""
    return _get_registry().describe()


@mcp.tool()
def get_skill(name: str) -> str:
    """Return full details for a skill as JSON: description, required inputs, template.

    Args:
        name: Skill name (use list_skills to enumerate available names).
    """
    try:
        skill = _get_registry().get(name)
    except KeyError as exc:
        return f"Error: {exc}"
    return json.dumps(
        {
            "name": skill.name,
            "description": skill.description,
            "inputs": skill.inputs,
            "template": skill.template,
        },
        indent=2,
    )


@mcp.tool()
def render_skill(name: str, inputs: dict[str, str]) -> str:
    """Render a skill template by substituting the provided inputs.

    Returns the filled prompt text ready to pass to an LLM.

    Args:
        name:   Skill name.
        inputs: Key-value pairs matching the skill's declared ``inputs`` field.
                Call get_skill first to discover which keys are required.
    """
    try:
        skill = _get_registry().get(name)
        return skill.render(**inputs)
    except (KeyError, ValueError) as exc:
        return f"Error: {exc}"


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    mcp.run()  # transport="stdio" by default


if __name__ == "__main__":
    main()
