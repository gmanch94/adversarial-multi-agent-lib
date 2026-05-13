"""
Markdown-based skill registry (mirrors ARIS §3.1 — 65+ skills via MCP).

Security properties:
- Skill names validated against a strict charset (no path traversal, no empty,
  no whitespace, capped length). Collisions raise instead of silently
  overwriting (HIGH-6).
- Skill bodies bounded in length (HIGH-6).
- Frontmatter `---` delimiters are line-anchored — `---` inside values does
  not split the parse (LOW-2).
- Skills directory is resolved to an absolute path and only `.md` files
  directly inside it are loaded (no recursion, no symlink escape) (HIGH-5).
- `Skill.render` uses `format_map` with passthrough dict — literal `{tokens}`
  outside declared inputs are left intact, not raising KeyError (CRIT-1
  follow-on from earlier triage).
- A warning is emitted for malformed skill files instead of silent skip.
"""
from __future__ import annotations

import importlib.resources
import re
import warnings
from dataclasses import dataclass
from pathlib import Path
from typing import Any


_VALID_SKILL_NAME = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")
_MAX_TEMPLATE_CHARS = 50_000
_MAX_DESCRIPTION_CHARS = 500


class _PartialFormat(dict[str, str]):
    """format_map helper: substitutes declared keys, leaves unknown {tokens} intact."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


@dataclass
class Skill:
    name: str
    description: str
    inputs: list[str]
    template: str       # prompt template with {input_name} placeholders; literal { } must be doubled
    path: Path

    def render(self, **kwargs: Any) -> str:
        """Render the skill template with provided inputs.

        Uses format_map with a passthrough dict so that {tokens} not in `inputs`
        (e.g. JSON examples, LaTeX, code blocks) are left verbatim instead of
        raising KeyError.
        """
        missing = [k for k in self.inputs if k not in kwargs]
        if missing:
            raise ValueError(f"Skill '{self.name}' missing inputs: {missing}")
        return self.template.format_map(_PartialFormat(**kwargs))


class SkillRegistry:
    """
    Loads and indexes all *.md skill files from a directory.

    Construction never silently ignores invalid input — a malformed file
    triggers a UserWarning so misconfiguration is visible.
    """

    def __init__(self, skills_dir: str = "skills") -> None:
        self._dir = Path(skills_dir).expanduser().resolve()
        self._skills: dict[str, Skill] = {}
        self._load()

    def _load(self) -> None:
        if not self._dir.is_dir():
            return
        # Non-recursive glob — only files directly inside skills/
        for md_file in sorted(self._dir.glob("*.md")):
            # Reject symlinks pointing outside the dir (defence-in-depth)
            try:
                resolved = md_file.resolve()
                resolved.relative_to(self._dir)
            except (OSError, ValueError):
                warnings.warn(
                    f"Skipping {md_file}: resolves outside skills directory",
                    UserWarning,
                    stacklevel=2,
                )
                continue
            try:
                skill = self._parse(md_file)
            except ValueError as exc:
                warnings.warn(
                    f"Skipping {md_file}: {exc}", UserWarning, stacklevel=2
                )
                continue
            if skill is None:
                warnings.warn(
                    f"Skipping {md_file}: missing or malformed frontmatter",
                    UserWarning,
                    stacklevel=2,
                )
                continue
            if skill.name in self._skills:
                raise ValueError(
                    f"duplicate skill name '{skill.name}' "
                    f"(from {skill.path} and {self._skills[skill.name].path})"
                )
            self._skills[skill.name] = skill

    def _parse(self, path: Path) -> Skill | None:
        text = path.read_text(encoding="utf-8")
        fm, body = self._split_frontmatter(text)
        if fm is None:
            return None

        name = fm.get("name", path.stem)
        if not isinstance(name, str) or not _VALID_SKILL_NAME.match(name):
            raise ValueError(
                f"invalid skill name '{name}' — must match {_VALID_SKILL_NAME.pattern}"
            )

        description = fm.get("description", "")
        if not isinstance(description, str):
            description = str(description)
        if len(description) > _MAX_DESCRIPTION_CHARS:
            raise ValueError(
                f"description length {len(description)} exceeds max {_MAX_DESCRIPTION_CHARS}"
            )

        inputs_raw = fm.get("inputs", [])
        if isinstance(inputs_raw, list):
            inputs = [str(i) for i in inputs_raw]
        elif isinstance(inputs_raw, str):
            inputs = [inputs_raw]
        else:
            inputs = []
        # Each input name must be a Python identifier (used as format key)
        for inp in inputs:
            if not inp.isidentifier():
                raise ValueError(
                    f"invalid input name '{inp}' — must be a valid Python identifier"
                )

        body_stripped = body.strip()
        if len(body_stripped) > _MAX_TEMPLATE_CHARS:
            raise ValueError(
                f"template length {len(body_stripped)} exceeds max {_MAX_TEMPLATE_CHARS}"
            )

        return Skill(
            name=name,
            description=description,
            inputs=inputs,
            template=body_stripped,
            path=path,
        )

    @staticmethod
    def _split_frontmatter(text: str) -> tuple[dict[str, Any] | None, str]:
        """Split YAML frontmatter from body. The opening and closing `---`
        must each occupy a line on their own — `---` appearing inside a value
        will not be treated as the terminator (LOW-2)."""
        lines = text.splitlines()
        if not lines or lines[0].strip() != "---":
            return None, text
        # Find the closing `---` on its own line, starting from line 1
        end_idx = -1
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                end_idx = i
                break
        if end_idx == -1:
            return None, text
        fm_text = "\n".join(lines[1:end_idx])
        body = "\n".join(lines[end_idx + 1:])
        fm = SkillRegistry._parse_simple_yaml(fm_text)
        return fm, body

    @staticmethod
    def _parse_simple_yaml(text: str) -> dict[str, Any]:
        """Minimal YAML: string scalars and inline lists. Single-line values only."""
        result: dict[str, Any] = {}
        for line in text.splitlines():
            line = line.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if ":" not in stripped:
                continue
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            if value.startswith("[") and value.endswith("]"):
                items = [v.strip().strip("'\"") for v in value[1:-1].split(",") if v.strip()]
                result[key] = items
            else:
                result[key] = value.strip("'\"")
        return result

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, name: str) -> Skill:
        if name not in self._skills:
            raise KeyError(f"Skill '{name}' not found. Available: {list(self._skills)}")
        return self._skills[name]

    def list(self) -> list[str]:
        return sorted(self._skills.keys())

    def describe(self) -> str:
        lines = [f"Available skills ({len(self._skills)}):"]
        for name, skill in sorted(self._skills.items()):
            lines.append(f"  {name}: {skill.description}")
        return "\n".join(lines)

    def reload(self) -> None:
        self._skills.clear()
        self._load()

    @staticmethod
    def bundled_skills_path(domain: str = "research") -> Path:
        """Return the path to the bundled skill templates for the given domain.

        Args:
            domain: Use-case domain — ``"research"`` (default) or ``"parole"``.
                    Maps to ``adv_multi_agent.<domain>.skills.templates``.
        """
        pkg = f"adv_multi_agent.{domain}.skills"
        return Path(str(importlib.resources.files(pkg).joinpath("templates")))
