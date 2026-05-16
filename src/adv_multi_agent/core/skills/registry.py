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

# H3/H4: bound caller-supplied input dict at the Skill.render chokepoint so
# every consumer (MCP server, programmatic caller, tests) inherits the same
# guarantees. A 10 MB input value otherwise produces a 10 MB prompt and the
# MCP transport returns it verbatim.
_MAX_INPUT_VALUE_CHARS = 8_192
_MAX_INPUT_KEYS = 64
_CONTROL_CHARS_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x9b]")
# L-PC-4: strip `{` and `}` from caller-supplied input values before
# substitution. _PartialFormat passes through unknown `{xyz}` tokens unchanged,
# so a brace-laden input could smuggle format-syntax into the rendered prompt
# and influence the consuming LLM's parsing. Strip outright — callers should
# not pass brace-laden content into a skill input.
_BRACE_CHARS_RE = re.compile(r"[{}]")


class _PartialFormat(dict[str, str]):
    """format_map helper: substitutes declared keys, leaves unknown {tokens} intact."""
    def __missing__(self, key: str) -> str:
        return f"{{{key}}}"


_VALID_VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+-]{0,31}$")


@dataclass
class Skill:
    name: str
    description: str
    inputs: list[str]
    template: str       # prompt template with {input_name} placeholders; literal { } must be doubled
    path: Path
    # M11: optional skill version. Charset and length are bounded
    # (matches `_VALID_VERSION_RE`); absent or unparseable values default
    # to "1.0.0" so existing skill files without a version still load.
    version: str = "1.0.0"

    def render(self, **kwargs: Any) -> str:
        """Render the skill template with provided inputs.

        Uses format_map with a passthrough dict so that {tokens} not in `inputs`
        (e.g. JSON examples, LaTeX, code blocks) are left verbatim instead of
        raising KeyError.

        H3/H4: caller-supplied input values are bounded in count, per-value
        length, and stripped of control characters before substitution. This
        chokepoint protects every consumer (MCP server, library caller, tests)
        from DoS via 10 MB values and terminal-injection via ANSI escapes.
        """
        if len(kwargs) > _MAX_INPUT_KEYS:
            raise ValueError(
                f"too many input keys: {len(kwargs)} (max {_MAX_INPUT_KEYS})"
            )
        sanitized: dict[str, str] = {}
        for key, value in kwargs.items():
            if not isinstance(value, str):
                value = str(value)
            if len(value) > _MAX_INPUT_VALUE_CHARS:
                raise ValueError(
                    f"input '{key}' length {len(value)} exceeds "
                    f"max {_MAX_INPUT_VALUE_CHARS} chars"
                )
            stripped = _CONTROL_CHARS_RE.sub("", value)
            # L-PC-4: strip braces to prevent format-syntax smuggling.
            sanitized[key] = _BRACE_CHARS_RE.sub("", stripped)
        missing = [k for k in self.inputs if k not in sanitized]
        if missing:
            raise ValueError(f"Skill '{self.name}' missing inputs: {missing}")
        return self.template.format_map(_PartialFormat(**sanitized))


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

        # M11: optional `version` frontmatter field, charset-bounded.
        version_raw = fm.get("version", "1.0.0")
        if not isinstance(version_raw, str):
            version_raw = str(version_raw)
        if not _VALID_VERSION_RE.match(version_raw):
            raise ValueError(
                f"invalid skill version '{version_raw}' — must match "
                f"{_VALID_VERSION_RE.pattern}"
            )

        return Skill(
            name=name,
            description=description,
            inputs=inputs,
            template=body_stripped,
            path=path,
            version=version_raw,
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
    def _strip_balanced_quotes(value: str) -> str:
        """M8: strip a single matched pair of surrounding quotes, not arbitrary
        leading/trailing quote chars. `'a"b'` -> `a"b`. `"hi"` -> `hi`. `a"b`
        stays `a"b` (no balanced wrapper)."""
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            return value[1:-1]
        return value

    @staticmethod
    def _parse_simple_yaml(text: str) -> dict[str, Any]:
        """Minimal YAML: string scalars, inline lists, and block scalars (`|`).

        M7: duplicate keys raise instead of silently overwriting.
        M8: quote stripping is balanced (matched pair only).
        M10: a value of `|` opens a block scalar — subsequent lines that
        are indented more than the key are joined with `\\n` until a
        less-indented line or EOF. `>` (folded) is treated identically
        with single-space joining.
        """
        result: dict[str, Any] = {}
        raw_lines = text.splitlines()
        i = 0
        while i < len(raw_lines):
            raw = raw_lines[i]
            line = raw.rstrip()
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                i += 1
                continue
            if ":" not in stripped:
                i += 1
                continue
            # Preserve key indentation for block-scalar comparison.
            key_indent = len(line) - len(line.lstrip(" "))
            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip()
            if not key:
                i += 1
                continue
            if key in result:
                raise ValueError(f"duplicate key in skill frontmatter: {key!r}")
            # Block scalar: `|` (literal, preserve newlines) or `>` (folded,
            # join with spaces). Indented continuation lines are gathered
            # until a less-or-equally-indented non-blank line.
            if value in ("|", ">"):
                joiner = "\n" if value == "|" else " "
                block: list[str] = []
                j = i + 1
                while j < len(raw_lines):
                    cont = raw_lines[j]
                    cont_stripped = cont.strip()
                    if not cont_stripped:
                        block.append("")
                        j += 1
                        continue
                    cont_indent = len(cont) - len(cont.lstrip(" "))
                    if cont_indent <= key_indent:
                        break
                    block.append(cont.lstrip(" "))
                    j += 1
                # Drop trailing blanks so terminating newlines don't leak.
                while block and block[-1] == "":
                    block.pop()
                result[key] = joiner.join(block)
                i = j
                continue
            if value.startswith("[") and value.endswith("]"):
                items = [
                    SkillRegistry._strip_balanced_quotes(v.strip())
                    for v in value[1:-1].split(",")
                    if v.strip()
                ]
                result[key] = items
            else:
                result[key] = SkillRegistry._strip_balanced_quotes(value)
            i += 1
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

    # L-IND-4: allowlist prevents confusing importlib errors on typos and
    # blocks path-traversal attempts (e.g. domain="research..").
    _KNOWN_DOMAINS: frozenset[str] = frozenset(
        {"research", "parole", "retail", "pc", "industrial", "healthcare"}
    )

    @staticmethod
    def bundled_skills_path(domain: str = "research") -> Path:
        """Return the path to the bundled skill templates for the given domain.

        Args:
            domain: Use-case domain — one of ``"research"``, ``"parole"``,
                    ``"retail"``, ``"pc"``, ``"industrial"``, or ``"healthcare"``
                    (default: ``"research"``). Maps to
                    ``adv_multi_agent.<domain>.skills.templates``.

        Raises:
            ValueError: If *domain* is not a recognised domain name.
        """
        if domain not in SkillRegistry._KNOWN_DOMAINS:
            raise ValueError(
                f"Unknown domain {domain!r}. "
                f"Must be one of: {sorted(SkillRegistry._KNOWN_DOMAINS)}"
            )
        pkg = f"adv_multi_agent.{domain}.skills"
        return Path(str(importlib.resources.files(pkg).joinpath("templates")))
